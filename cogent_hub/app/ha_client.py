"""Home Assistant WebSocket client.

Connects to Core through the Supervisor proxy, authenticates with the supervisor
token, subscribes to ``state_changed`` events, and exposes ``call_service`` for the
Phase 2 cloud-to-device command path.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Optional

import aiohttp

_LOG = logging.getLogger(__name__)


class HAClient:
    def __init__(self, ws_url: str, token: str, session: aiohttp.ClientSession):
        self._ws_url = ws_url
        self._token = token
        self._session = session
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._msg_id = 0
        self._lock = asyncio.Lock()

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    async def connect(self) -> None:
        """Open the socket and complete the auth handshake."""
        self._ws = await self._session.ws_connect(self._ws_url, heartbeat=30)
        # 1) auth_required
        msg = await self._ws.receive_json()
        if msg.get("type") != "auth_required":
            raise RuntimeError(f"Unexpected first frame: {msg.get('type')}")
        # 2) send auth
        await self._ws.send_json({"type": "auth", "access_token": self._token})
        # 3) auth_ok / auth_invalid
        msg = await self._ws.receive_json()
        if msg.get("type") != "auth_ok":
            raise RuntimeError(f"Authentication failed: {msg}")
        _LOG.info("connected to Home Assistant (%s)", msg.get("ha_version", "?"))

    async def subscribe_state_changed(self) -> int:
        sub_id = self._next_id()
        await self._ws.send_json(
            {"id": sub_id, "type": "subscribe_events", "event_type": "state_changed"}
        )
        # Expect a result frame confirming the subscription.
        while True:
            msg = await self._ws.receive_json()
            if msg.get("id") == sub_id and msg.get("type") == "result":
                if not msg.get("success", False):
                    raise RuntimeError(f"subscribe_events failed: {msg}")
                _LOG.info("subscribed to state_changed events")
                return sub_id

    async def events(self) -> AsyncIterator[dict]:
        """Yield raw HA event payloads (the ``event`` dict of each event frame)."""
        assert self._ws is not None
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = msg.json()
                if data.get("type") == "event":
                    yield data["event"]
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break

    async def call_service(
        self, domain: str, service: str, service_data: Optional[dict] = None,
        target: Optional[dict] = None,
    ) -> dict:
        """Phase 2: execute a service call on the hub (e.g. switch.turn_on).

        Returns the HA ``result`` frame. Safe to call concurrently with the event
        stream because each call uses a unique message id.
        """
        async with self._lock:
            call_id = self._next_id()
            payload = {
                "id": call_id,
                "type": "call_service",
                "domain": domain,
                "service": service,
            }
            if service_data:
                payload["service_data"] = service_data
            if target:
                payload["target"] = target
            await self._ws.send_json(payload)
            while True:
                msg = await self._ws.receive_json()
                if msg.get("id") == call_id and msg.get("type") == "result":
                    return msg

    async def close(self) -> None:
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()

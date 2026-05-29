"""Cogent Cloud HTTP client.

POSTs batched telemetry to the Cogent Open API. Authentication uses the ``APIKey``
header, matching the Cogent API convention; the server validates it against
``SEC_AccountAPIKeys`` and resolves the owning account.
"""

from __future__ import annotations

import logging
from typing import Optional

import aiohttp

_LOG = logging.getLogger(__name__)


class CloudClient:
    def __init__(self, telemetry_url: str, api_key: str, session: aiohttp.ClientSession,
                 commands_url: Optional[str] = None):
        self._url = telemetry_url
        self._api_key = api_key
        self._session = session
        self._commands_url = commands_url

    async def send_batch(self, hub_id: str, events: list[dict], batch_id: str) -> bool:
        """Send one telemetry batch. Returns True on 2xx, False on a retryable failure.

        Raises nothing — transport/HTTP errors are logged and reported as False so the
        caller can re-spool. A 4xx other than 408/429 is treated as non-retryable but
        still returns False (the batch is dropped by the caller to avoid poison loops).
        """
        payload = {
            "hub_id": hub_id,
            "batch_id": batch_id,
            "events": events,
        }
        headers = {"APIKey": self._api_key, "Content-Type": "application/json"}
        try:
            async with self._session.post(
                self._url, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if 200 <= resp.status < 300:
                    return True
                body = (await resp.text())[:300]
                _LOG.warning("telemetry POST -> HTTP %s: %s", resp.status, body)
                return False
        except (aiohttp.ClientError, OSError) as exc:
            _LOG.warning("telemetry POST failed: %s", exc)
            return False

    # ---- Phase 2: cloud -> device control ----

    async def fetch_commands(self, hub_id: str) -> list[dict]:
        """Poll for pending commands for this hub. Returns a list (empty on error)."""
        if not self._commands_url:
            return []
        headers = {"APIKey": self._api_key}
        try:
            async with self._session.get(
                self._commands_url, params={"hub_id": hub_id}, headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data if isinstance(data, list) else []
                if resp.status in (401, 403):
                    _LOG.warning("commands GET -> HTTP %s (check cloud_api_key)", resp.status)
                else:
                    _LOG.debug("commands GET -> HTTP %s", resp.status)
                return []
        except (aiohttp.ClientError, OSError) as exc:
            _LOG.debug("commands GET failed: %s", exc)
            return []

    async def ack_command(self, command_id, ok: bool, result: Optional[str] = None,
                          error: Optional[str] = None) -> bool:
        """Report a command's execution result back to the cloud."""
        if not self._commands_url:
            return False
        url = f"{self._commands_url}/{command_id}/ack"
        headers = {"APIKey": self._api_key, "Content-Type": "application/json"}
        payload = {"ok": ok, "result": result, "error": error}
        try:
            async with self._session.post(
                url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                return 200 <= resp.status < 300
        except (aiohttp.ClientError, OSError) as exc:
            _LOG.warning("command ack failed: %s", exc)
            return False

    @staticmethod
    def is_fatal_status_retryable(status: int) -> bool:
        return status in (408, 429) or 500 <= status < 600

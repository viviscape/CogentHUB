"""Phase 2: cloud -> device command execution.

The cloud queues commands; the appliance polls (``CloudClient.fetch_commands``), validates
each against an allowlist, executes it via the Home Assistant REST API
(``POST /api/services/{domain}/{service}``), and acks the result back.

REST (not the event WebSocket) is used for service calls so command execution never
races the telemetry event stream.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import aiohttp

_LOG = logging.getLogger(__name__)


class CommandExecutor:
    """Validates and executes cloud-issued commands via the HA REST API."""

    def __init__(self, session: aiohttp.ClientSession, rest_url: str, token: str, allowed_domains):
        self._session = session
        self._rest_url = (rest_url or "").rstrip("/")
        self._token = token
        self._allowed = set(allowed_domains or [])

    async def execute(self, command: dict) -> dict:
        """Execute one command; return ``{ok, result, error}``."""
        domain = (command.get("domain") or "").strip()
        service = (command.get("service") or "").strip()
        entity_id = command.get("entity_id")
        data = command.get("service_data") or {}

        if not domain or not service:
            return {"ok": False, "error": "domain and service are required"}
        if domain not in self._allowed:
            return {"ok": False, "error": f"domain '{domain}' not in allowlist {sorted(self._allowed)}"}

        body = dict(data)
        if entity_id:
            body["entity_id"] = entity_id
        url = f"{self._rest_url}/services/{domain}/{service}"
        headers = {"Authorization": "Bearer " + self._token, "Content-Type": "application/json"}
        try:
            async with self._session.post(
                url, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                text = await resp.text()
                if 200 <= resp.status < 300:
                    return {"ok": True, "result": text[:1000]}
                return {"ok": False, "error": f"HTTP {resp.status}: {text[:300]}"}
        except (aiohttp.ClientError, OSError) as exc:
            return {"ok": False, "error": str(exc)}


async def command_loop(cfg, cloud, executor: CommandExecutor, stop: asyncio.Event) -> None:
    """Poll the cloud for commands, execute each, and ack. Runs until ``stop`` is set."""
    _LOG.info("command channel enabled — polling %s every %ds (allowlist: %s)",
              cfg.commands_url, cfg.command_poll_interval,
              ",".join(sorted(cfg.controllable_domains)) or "none")
    while not stop.is_set():
        try:
            cmds = await cloud.fetch_commands(cfg.hub_id)
            for cmd in cmds:
                cid = cmd.get("id")
                res = await executor.execute(cmd)
                await cloud.ack_command(cid, res.get("ok", False), res.get("result"), res.get("error"))
                if res.get("ok"):
                    _LOG.info("command %s done: %s.%s -> %s", cid,
                              cmd.get("domain"), cmd.get("service"), cmd.get("entity_id"))
                else:
                    _LOG.warning("command %s failed: %s", cid, res.get("error"))
        except Exception as exc:  # noqa: BLE001 — keep the loop alive
            _LOG.debug("command poll error: %s", exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=cfg.command_poll_interval)
        except asyncio.TimeoutError:
            pass

"""Phase 2 (scaffold): cloud-to-device command execution.

Goal: let Cogent Cloud issue triggers that this add-on executes on the hub by calling
Home Assistant services (switch.turn_on, light.toggle, scene.turn_on, ...).

Design notes for the implementer:

* Transport — open a persistent outbound channel to the cloud so commands can be
  pushed in real time without inbound firewall holes. Options:
    - WebSocket / SignalR hub on the Cogent side (preferred; matches CogentCloudMCP), or
    - long-poll ``GET /api/v1/hub/commands?hub_id=...`` returning queued commands, then
      ``POST /api/v1/hub/commands/{id}/ack`` with the result.

* Command shape (proposed, snake_case):
    {
      "command_id": "uuid",
      "domain": "switch",            # HA domain
      "service": "turn_on",          # HA service
      "target": {"entity_id": "switch.front_porch"},
      "service_data": {}             # optional
    }

* Execution — call ``HAClient.call_service(domain, service, service_data, target)`` and
  report success/failure back to the cloud via the ack endpoint.

* IMPORTANT (concurrency): the Phase 1 event reader is currently the sole consumer of
  the WebSocket. Before enabling live ``call_service`` against the same socket, refactor
  ``HAClient`` to a single-reader/dispatch-by-id model (one task reads every frame and
  routes ``result`` frames to pending futures keyed by message id). Otherwise the
  command's result frame races the event stream.

* Safety — enforce an allowlist of domains/entities the cloud may control, and validate
  every command against ``include_domains`` / an explicit ``controllable`` allowlist
  before execution.
"""

from __future__ import annotations

import logging

from .ha_client import HAClient

_LOG = logging.getLogger(__name__)

# Domains Cogent Cloud is permitted to control on this hub (Phase 2 default allowlist).
DEFAULT_CONTROLLABLE_DOMAINS = {"switch", "light", "scene", "script", "input_boolean"}


class CommandExecutor:
    """Validates and executes cloud-issued commands. Not yet wired into main()."""

    def __init__(self, ha: HAClient, allowed_domains: set[str] | None = None):
        self._ha = ha
        self._allowed = allowed_domains or set(DEFAULT_CONTROLLABLE_DOMAINS)

    async def execute(self, command: dict) -> dict:
        domain = command.get("domain", "")
        service = command.get("service", "")
        if domain not in self._allowed:
            return {"command_id": command.get("command_id"), "ok": False,
                    "error": f"domain '{domain}' not in allowlist"}
        result = await self._ha.call_service(
            domain, service,
            service_data=command.get("service_data"),
            target=command.get("target"),
        )
        ok = bool(result.get("success"))
        return {"command_id": command.get("command_id"), "ok": ok, "result": result}

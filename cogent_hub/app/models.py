"""Normalization of Home Assistant events into the Cogent telemetry wire format.

The wire format is snake_case JSON to match the Cogent API conventions.
"""

from __future__ import annotations

from typing import Optional


def domain_of(entity_id: str) -> str:
    return entity_id.split(".", 1)[0] if "." in entity_id else entity_id


def normalize_state_changed(event_data: dict, send_attributes: bool) -> Optional[dict]:
    """Map a Home Assistant ``state_changed`` event to a telemetry event.

    Returns ``None`` for events that carry no useful new state.
    """
    entity_id = event_data.get("entity_id")
    new_state = event_data.get("new_state")
    old_state = event_data.get("old_state")

    if not entity_id or new_state is None:
        # entity removed / no new state — skip.
        return None

    evt = {
        "event_type": "state_changed",
        "entity_id": entity_id,
        "domain": domain_of(entity_id),
        "state": new_state.get("state"),
        "previous_state": (old_state or {}).get("state"),
        "occurred_at": new_state.get("last_changed") or new_state.get("last_updated"),
    }

    if send_attributes:
        attrs = new_state.get("attributes") or {}
        if attrs:
            evt["attributes"] = attrs

    return evt

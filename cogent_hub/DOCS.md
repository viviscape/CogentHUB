# Cogent Hub Connector

Streams Home Assistant telemetry to the Cogent Cloud API. Runs as an on-device add-on.

## Configuration

| Option | Default | Description |
|---|---|---|
| `cloud_base_url` | `https://api.cogentlog.io` | Base URL of the Cogent Open API. |
| `cloud_api_key` | _(empty)_ | Account API key. Sent as the `APIKey` header; validated server-side. |
| `hub_id` | `Hub1` | Stable identifier for this hub. |
| `include_domains` | `sensor, binary_sensor, switch, light` | Only stream these entity domains. Empty = all. |
| `exclude_entities` | _(empty)_ | Entity IDs to never stream. |
| `send_attributes` | `true` | Include each entity's attributes in events. |
| `batch_size` | `50` | Max events per POST; also triggers an early flush. |
| `flush_interval_seconds` | `10` | Flush at least this often. |
| `max_spool_events` | `50000` | Cap on buffered/spooled events; oldest dropped first. |
| `log_level` | `info` | `trace`..`fatal`. |

## What it sends

`POST {cloud_base_url}/api/v1/hub/telemetry` with header `APIKey: <cloud_api_key>`:

```json
{
  "hub_id": "Hub1",
  "batch_id": "0f1c...",
  "events": [
    {
      "event_type": "state_changed",
      "entity_id": "switch.front_porch",
      "domain": "switch",
      "state": "on",
      "previous_state": "off",
      "occurred_at": "2026-05-29T14:00:00.000000+00:00",
      "attributes": { "friendly_name": "Front Porch" }
    }
  ]
}
```

## Durability

Events that can't be delivered are written to `/data/spool.jsonl` and retried with
exponential backoff. The spool is replayed on restart, so a cloud or network outage
doesn't lose data (up to `max_spool_events`).

## Local development (outside the Supervisor)

Set environment variables instead of `/data/options.json`:

```
HA_WS_URL=ws://192.168.1.39:8123/api/websocket
HA_TOKEN=<long-lived access token>
CLOUD_BASE_URL=https://api.cogentlog.io
CLOUD_API_KEY=<account api key>
HUB_ID=Hub1
python -m app.main
```

## Phase 2 (planned)

Cloud-issued device control. See `app/commands.py` for the design and the
`HAClient.call_service` hook already in place.

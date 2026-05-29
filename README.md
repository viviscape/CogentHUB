# CogentHUB

Home Assistant ↔ Cogent Cloud integration.

This repository is a **Home Assistant add-on repository**. The add-on (`cogent_hub`) is
an on-device appliance that runs on a Home Assistant OS / Supervised install and:

- **Phase 1 (implemented):** streams Home Assistant telemetry (entity state changes) to the
  Cogent Cloud API (`POST /api/v1/hub/telemetry`).
- **Phase 2 (scaffolded):** receives triggers from Cogent Cloud and executes them on the hub
  (calls Home Assistant services to control switches, lights, scenes, etc.). See
  `cogent_hub/app/commands.py`.

## Install on a hub

1. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**.
2. Add this repository URL.
3. Install **Cogent Hub Connector**, open **Configuration**, set:
   - `cloud_base_url` — e.g. `https://api.cogentlog.io`
   - `cloud_api_key` — the account API key (validated server-side against `SEC_AccountAPIKeys`)
   - `hub_id` — a stable identifier for this hub (e.g. `Hub1`)
4. **Start** the add-on. Check the **Log** tab for `connected` / `flushed N events`.

## Repository layout

```
repository.yaml             Add-on store metadata
cogent_hub/                 The add-on (appliance)
  config.yaml               Add-on manifest + user options schema
  build.yaml                Per-arch base images
  Dockerfile
  run.sh                    Entrypoint (exports env, launches app)
  requirements.txt
  DOCS.md                   In-UI documentation
  app/                      Python source
    main.py                 Async orchestration
    config.py               Loads /data/options.json + supervisor token
    ha_client.py            HA WebSocket client (subscribe events, call services)
    cloud_client.py         Cogent Cloud HTTP client (batched telemetry POST)
    batcher.py              Batching + store-and-forward spool
    models.py               Event normalization
    commands.py             Phase 2: cloud → device command execution (scaffold)
cloud/                      Notes for the cloud (Cogent.API.Open) side
  README.md                 What was added, and where, in Cogent Enterprise Advanced
```

## Cloud side

The ingestion endpoint lives in the **Cogent Enterprise Advanced** solution
(`Cogent.API.Open`, published at `https://api.cogentlog.io`):
`POST /api/v1/hub/telemetry`, authenticated with the `APIKey` header (handled globally by
`ApiKeyHandler`). See `cloud/README.md` for the exact files and the DB migration.

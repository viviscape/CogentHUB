# Standalone Docker deployment

Run the Cogent Hub Connector as a plain Docker container on any always-on host
(bypasses the Home Assistant add-on Supervisor entirely). Same Python app as the
add-on; config comes from environment variables instead of `/data/options.json`.

## Prerequisites
- Docker on the host.
- A Home Assistant **long-lived access token** (HA → profile → Security → Long-lived tokens).
- A **Cogent account API key** (validated server-side against `SEC_AccountAPIKeys`).
- Network reachability from the host to both the hub (`192.168.1.39:8123`) and `api.cogentlog.io`.

## Run
```bash
cd docker
cp .env.example .env
#   edit .env: set HA_TOKEN and CLOUD_API_KEY (HA_WS_URL/HUB_ID already default to Hub1)
docker compose up -d --build
docker compose logs -f
```
Healthy log lines: `connected to Home Assistant (...)`, `subscribed to state_changed events`,
then `flushed N events (...)` as state changes occur.

## Without compose
```bash
docker build -f docker/Dockerfile -t cogenthub:latest .
docker run -d --name cogent-hub --restart unless-stopped \
  -e HA_WS_URL=ws://192.168.1.39:8123/api/websocket \
  -e HA_TOKEN=<long-lived-token> \
  -e CLOUD_BASE_URL=https://api.cogentlog.io \
  -e CLOUD_API_KEY=<cogent-api-key> \
  -e HUB_ID=Hub1 \
  -v cogent-hub-data:/data \
  cogenthub:latest
```

## Notes
- Undelivered events spool to `/data/spool.jsonl` (the `cogent-hub-data` volume) and replay on restart.
- This path needs no Supervisor update; it's the recommended interim while Hub1's
  Supervisor is repaired (see project notes). Once the Supervisor is healthy, the
  same code installs as a managed add-on from `cogent_hub/`.

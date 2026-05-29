"""Add-on configuration.

When running as a Home Assistant add-on, user options are written by the Supervisor
to ``/data/options.json`` and the Core API is reachable through the Supervisor proxy
using ``SUPERVISOR_TOKEN``. For local development, the same values can be supplied via
environment variables (see ``_env_fallback``).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

OPTIONS_PATH = "/data/options.json"
SPOOL_PATH = "/data/spool.jsonl"

# Home Assistant Core, reached via the Supervisor proxy from inside an add-on.
SUPERVISOR_WS_URL = "ws://supervisor/core/websocket"
SUPERVISOR_REST_URL = "http://supervisor/core/api"

_LOG = logging.getLogger(__name__)

_LEVELS = {
    "trace": logging.DEBUG,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "fatal": logging.CRITICAL,
}


@dataclass
class Config:
    cloud_base_url: str
    cloud_api_key: str
    hub_id: str
    include_domains: list[str] = field(default_factory=list)
    exclude_entities: set[str] = field(default_factory=set)
    send_attributes: bool = True
    batch_size: int = 50
    flush_interval_seconds: int = 10
    max_spool_events: int = 50000
    log_level: str = "info"

    # Phase 2: cloud -> device control.
    enable_commands: bool = True
    command_poll_interval: int = 5
    controllable_domains: list[str] = field(default_factory=list)

    # Connection to Home Assistant Core.
    supervisor_token: str = ""
    ha_ws_url: str = SUPERVISOR_WS_URL
    ha_rest_url: str = SUPERVISOR_REST_URL
    spool_path: str = SPOOL_PATH

    @property
    def telemetry_url(self) -> str:
        return f"{self.cloud_base_url.rstrip('/')}/api/v1/hub/telemetry"

    @property
    def commands_url(self) -> str:
        return f"{self.cloud_base_url.rstrip('/')}/api/v1/hub/commands"

    @property
    def py_log_level(self) -> int:
        return _LEVELS.get(self.log_level.lower(), logging.INFO)


def _load_options() -> dict:
    if os.path.exists(OPTIONS_PATH):
        with open(OPTIONS_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return _env_fallback()


def _env_fallback() -> dict:
    """Allow running outside the Supervisor (local dev / tests)."""
    return {
        "cloud_base_url": os.getenv("CLOUD_BASE_URL", "https://api.cogentlog.io"),
        "cloud_api_key": os.getenv("CLOUD_API_KEY", ""),
        "hub_id": os.getenv("HUB_ID", "Hub1"),
        "include_domains": _split(os.getenv("INCLUDE_DOMAINS", "")),
        "exclude_entities": _split(os.getenv("EXCLUDE_ENTITIES", "")),
        "send_attributes": _as_bool(os.getenv("SEND_ATTRIBUTES", "true")),
        "batch_size": int(os.getenv("BATCH_SIZE", "50")),
        "flush_interval_seconds": int(os.getenv("FLUSH_INTERVAL_SECONDS", "10")),
        "max_spool_events": int(os.getenv("MAX_SPOOL_EVENTS", "50000")),
        "log_level": os.getenv("LOG_LEVEL", "info"),
        "enable_commands": _as_bool(os.getenv("ENABLE_COMMANDS", "true")),
        "command_poll_interval": int(os.getenv("COMMAND_POLL_INTERVAL", "5")),
        "controllable_domains": _split(os.getenv("CONTROLLABLE_DOMAINS", "")),
    }


# Domains the cloud may control by default (Phase 2 allowlist).
DEFAULT_CONTROLLABLE_DOMAINS = ["switch", "light", "scene", "script", "input_boolean"]


def _derive_rest_url(ws_url: str) -> str:
    """Derive the Core REST base from a WebSocket URL (standalone/dev mode)."""
    base = ws_url
    if base.startswith("ws://"):
        base = "http://" + base[len("ws://"):]
    elif base.startswith("wss://"):
        base = "https://" + base[len("wss://"):]
    # strip the websocket path, leaving .../api
    for suffix in ("/api/websocket", "/websocket"):
        if base.endswith(suffix):
            base = base[: -len(suffix)] + "/api"
            break
    return base


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _as_bool(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def load() -> Config:
    opts = _load_options()
    token = os.getenv("SUPERVISOR_TOKEN", "")

    # Local dev override: talk directly to a hub with a long-lived token.
    ws_url = os.getenv("HA_WS_URL", SUPERVISOR_WS_URL)
    if os.getenv("HA_REST_URL"):
        rest_url = os.environ["HA_REST_URL"]
    elif os.getenv("HA_WS_URL"):
        rest_url = _derive_rest_url(ws_url)  # standalone: derive REST from the WS URL
    else:
        rest_url = SUPERVISOR_REST_URL
    if os.getenv("HA_TOKEN"):
        token = os.environ["HA_TOKEN"]

    domains = list(opts.get("controllable_domains", []) or []) or list(DEFAULT_CONTROLLABLE_DOMAINS)

    cfg = Config(
        cloud_base_url=opts.get("cloud_base_url", "https://api.cogentlog.io"),
        cloud_api_key=opts.get("cloud_api_key", ""),
        hub_id=opts.get("hub_id", "Hub1"),
        include_domains=list(opts.get("include_domains", []) or []),
        exclude_entities=set(opts.get("exclude_entities", []) or []),
        send_attributes=bool(opts.get("send_attributes", True)),
        batch_size=int(opts.get("batch_size", 50)),
        flush_interval_seconds=int(opts.get("flush_interval_seconds", 10)),
        max_spool_events=int(opts.get("max_spool_events", 50000)),
        log_level=str(opts.get("log_level", "info")),
        enable_commands=bool(opts.get("enable_commands", True)),
        command_poll_interval=int(opts.get("command_poll_interval", 5)),
        controllable_domains=domains,
        supervisor_token=token,
        ha_ws_url=ws_url,
        ha_rest_url=rest_url,
    )

    if not cfg.cloud_api_key:
        _LOG.warning("cloud_api_key is empty — telemetry POSTs will be rejected (401).")
    if not cfg.supervisor_token:
        _LOG.warning("No SUPERVISOR_TOKEN/HA_TOKEN available — cannot authenticate to Home Assistant.")
    return cfg

"""Cogent Hub Connector — entrypoint.

Phase 1: subscribe to Home Assistant ``state_changed`` events, normalize and filter
them, then stream batches to the Cogent Cloud API with store-and-forward durability.
"""

from __future__ import annotations

import asyncio
import logging
import signal

import aiohttp

from . import config as config_mod
from .batcher import Batcher
from .cloud_client import CloudClient
from .ha_client import HAClient
from .models import domain_of, normalize_state_changed

_LOG = logging.getLogger("cogent_hub")


def _setup_logging(level: int) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _passes_filter(cfg: config_mod.Config, entity_id: str) -> bool:
    if entity_id in cfg.exclude_entities:
        return False
    if cfg.include_domains and domain_of(entity_id) not in cfg.include_domains:
        return False
    return True


async def _stream_events(cfg: config_mod.Config, session: aiohttp.ClientSession,
                         batcher: Batcher, stop: asyncio.Event) -> None:
    """Connect to HA and feed filtered events into the batcher; reconnect on failure."""
    backoff = 1
    while not stop.is_set():
        ha = HAClient(cfg.ha_ws_url, cfg.supervisor_token, session)
        try:
            await ha.connect()
            await ha.subscribe_state_changed()
            backoff = 1
            async for event in ha.events():
                if stop.is_set():
                    break
                data = event.get("data", {})
                entity_id = data.get("entity_id", "")
                if not _passes_filter(cfg, entity_id):
                    continue
                normalized = normalize_state_changed(data, cfg.send_attributes)
                if normalized is not None:
                    batcher.add(normalized)
        except Exception as exc:  # noqa: BLE001 — keep the connector alive on any HA error
            if not stop.is_set():
                _LOG.warning("HA connection lost (%s); reconnecting in %ds", exc, backoff)
        finally:
            await ha.close()

        if stop.is_set():
            break
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)


async def amain() -> None:
    cfg = config_mod.load()
    _setup_logging(cfg.py_log_level)
    _LOG.info("Cogent Hub Connector starting — hub_id=%s, target=%s",
              cfg.hub_id, cfg.telemetry_url)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass  # not available on all platforms

    async with aiohttp.ClientSession() as session:
        cloud = CloudClient(cfg.telemetry_url, cfg.cloud_api_key, session)
        batcher = Batcher(
            cloud=cloud,
            hub_id=cfg.hub_id,
            batch_size=cfg.batch_size,
            flush_interval=cfg.flush_interval_seconds,
            spool_path=cfg.spool_path,
            max_spool_events=cfg.max_spool_events,
        )
        batcher.load_spool()

        flush_task = asyncio.create_task(batcher.run(), name="batcher")
        stream_task = asyncio.create_task(_stream_events(cfg, session, batcher, stop), name="stream")

        await stop.wait()
        _LOG.info("shutdown requested — draining...")

        stream_task.cancel()
        await batcher.stop()
        flush_task.cancel()
        for task in (stream_task, flush_task):
            try:
                await task
            except asyncio.CancelledError:
                pass

    _LOG.info("stopped.")


def main() -> None:
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

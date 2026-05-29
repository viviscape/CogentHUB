"""Batching + store-and-forward.

Incoming normalized events are queued, then flushed to the cloud in batches when the
batch size is reached or the flush interval elapses. Anything that fails to send is
written to a disk spool (``/data/spool.jsonl``) so it survives add-on restarts and is
retried later. The spool is bounded by ``max_spool_events`` (oldest dropped first).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections import deque

from .cloud_client import CloudClient

_LOG = logging.getLogger(__name__)


class Batcher:
    def __init__(
        self,
        cloud: CloudClient,
        hub_id: str,
        batch_size: int,
        flush_interval: int,
        spool_path: str,
        max_spool_events: int,
    ):
        self._cloud = cloud
        self._hub_id = hub_id
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._spool_path = spool_path
        self._max_spool = max_spool_events

        self._buffer: deque[dict] = deque()
        self._wake = asyncio.Event()
        self._running = False
        self._backoff = 1

    # -- ingestion -------------------------------------------------------------

    def add(self, event: dict) -> None:
        self._buffer.append(event)
        self._trim()
        if len(self._buffer) >= self._batch_size:
            self._wake.set()

    def _trim(self) -> None:
        if self._max_spool and len(self._buffer) > self._max_spool:
            drop = len(self._buffer) - self._max_spool
            for _ in range(drop):
                self._buffer.popleft()
            _LOG.warning("spool full — dropped %d oldest events", drop)

    # -- persistence -----------------------------------------------------------

    def load_spool(self) -> None:
        if not os.path.exists(self._spool_path):
            return
        try:
            with open(self._spool_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if line:
                        self._buffer.append(json.loads(line))
            self._trim()
            if self._buffer:
                _LOG.info("loaded %d spooled events from previous run", len(self._buffer))
                self._wake.set()
        except (OSError, ValueError) as exc:
            _LOG.warning("could not load spool: %s", exc)

    def _persist_spool(self) -> None:
        """Mirror the current buffer to disk so unsent events survive a restart."""
        try:
            tmp = self._spool_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                for evt in self._buffer:
                    handle.write(json.dumps(evt, separators=(",", ":")) + "\n")
            os.replace(tmp, self._spool_path)
        except OSError as exc:
            _LOG.warning("could not persist spool: %s", exc)

    # -- flush loop ------------------------------------------------------------

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self._flush_interval)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()
            await self._flush_once()

    async def _flush_once(self) -> None:
        if not self._buffer:
            return

        batch = [self._buffer.popleft() for _ in range(min(self._batch_size, len(self._buffer)))]
        batch_id = uuid.uuid4().hex
        ok = await self._cloud.send_batch(self._hub_id, batch, batch_id)

        if ok:
            _LOG.info("flushed %d events (batch %s); %d queued", len(batch), batch_id[:8], len(self._buffer))
            self._backoff = 1
            self._persist_spool()
            if self._buffer:
                self._wake.set()  # keep draining
        else:
            # Re-queue at the front and back off; persist so nothing is lost.
            self._buffer.extendleft(reversed(batch))
            self._trim()
            self._persist_spool()
            _LOG.warning("flush failed; %d events spooled, retrying in %ds", len(self._buffer), self._backoff)
            await asyncio.sleep(self._backoff)
            self._backoff = min(self._backoff * 2, 60)
            self._wake.set()

    async def stop(self) -> None:
        self._running = False
        self._wake.set()
        # Best-effort final flush to disk.
        self._persist_spool()

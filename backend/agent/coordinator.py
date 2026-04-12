"""Pipeline worker / coordinator entry point.

Consumes events from Redis Streams and executes pipeline steps.
This is a minimal stub that validates the container lifecycle.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from config.loader import load_config
from events.adapters.in_memory import InMemoryEventBus
from events.protocols import EventBus
from events.types import DocumentsUploadedEvent, EventBase
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.service import IngestionService
from storage.adapters.in_memory import InMemoryObjectStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("chili.worker")


def build_worker_dependencies() -> tuple[EventBus, IngestionService]:
    """Assemble the worker's ingestion dependencies.

    This uses in-memory adapters as a scaffolding step until Redis Streams and
    real object storage adapters are implemented.
    """
    load_config()
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    orchestrator = DocumentParsingOrchestrator(
        create_default_registry(),
        fetcher=HttpxRemoteDocumentFetcher(),
    )
    service = IngestionService(
        orchestrator,
        object_store=object_store,
        event_bus=event_bus,
    )
    return event_bus, service


def handle_event(event: EventBase, ingestion_service: IngestionService) -> int:
    """Handle a single event and return the number of processed documents."""
    if isinstance(event, DocumentsUploadedEvent):
        return len(ingestion_service.process_documents_uploaded(event))
    return 0


def drain_ingestion_events(
    event_bus: EventBus,
    ingestion_service: IngestionService,
    *,
    limit: int = 10,
) -> int:
    """Consume and process available ingestion events."""
    processed = 0
    for event in event_bus.consume(["docs.uploaded"], limit=limit):
        processed += handle_event(event, ingestion_service)
    return processed


async def run_worker() -> None:
    """Main worker loop — connects to Redis and processes events."""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    logger.info("Worker starting — REDIS_URL=%s", redis_url)
    event_bus, ingestion_service = build_worker_dependencies()

    # TODO: Replace with actual Redis Streams consumer once events/ module exists.
    try:
        while True:
            processed = drain_ingestion_events(event_bus, ingestion_service)
            if processed:
                logger.info("Processed %s ingestion document(s)", processed)
            await asyncio.sleep(5)
            logger.debug("Worker heartbeat")
    except asyncio.CancelledError:
        logger.info("Worker shutting down")


def main() -> None:
    """Entry point for `python -m agent.coordinator`."""
    logger.info("chiliAI pipeline worker starting")
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker interrupted — exiting")
        sys.exit(0)


if __name__ == "__main__":
    main()

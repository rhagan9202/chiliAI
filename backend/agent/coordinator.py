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
from events.protocols import EventBus, EventDelivery
from events.runtime import EventBusSettings, create_event_bus, load_event_bus_settings
from events.types import DocumentsUploadedEvent
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


def build_worker_dependencies() -> tuple[EventBus, IngestionService, EventBusSettings]:
    """Assemble the worker's ingestion dependencies.

    The event transport is selected at runtime so tests can keep using the
    in-memory adapter while deployed workers consume Redis Streams.
    """
    load_config()
    event_settings = load_event_bus_settings()
    event_bus = create_event_bus(event_settings)
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
    return event_bus, service, event_settings


def handle_event(delivery: EventDelivery, ingestion_service: IngestionService) -> int:
    """Handle a single event and return the number of processed documents."""
    event = delivery.event
    if isinstance(event, DocumentsUploadedEvent):
        return len(ingestion_service.process_documents_uploaded(event))
    return 0


def drain_ingestion_events(
    event_bus: EventBus,
    ingestion_service: IngestionService,
    *,
    consumer_group: str,
    consumer_name: str,
    limit: int = 10,
    block_ms: int | None = None,
) -> int:
    """Consume and process available ingestion events."""
    processed = 0
    event_types = ["documents.uploaded"]
    event_bus.ensure_consumer_group(event_types, consumer_group=consumer_group)
    deliveries = event_bus.consume(
        event_types,
        consumer_group=consumer_group,
        consumer_name=consumer_name,
        limit=limit,
        block_ms=block_ms,
    )
    ackable: list[EventDelivery] = []
    for delivery in deliveries:
        processed += handle_event(delivery, ingestion_service)
        ackable.append(delivery)
    if ackable:
        event_bus.ack(ackable)
    return processed


async def run_worker() -> None:
    """Main worker loop — connects to Redis and processes events."""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    logger.info("Worker starting — REDIS_URL=%s", redis_url)
    event_bus, ingestion_service, event_settings = build_worker_dependencies()

    try:
        while True:
            processed = drain_ingestion_events(
                event_bus,
                ingestion_service,
                consumer_group=event_settings.consumer_group,
                consumer_name=event_settings.consumer_name(),
                limit=event_settings.batch_size,
                block_ms=event_settings.block_ms,
            )
            if processed:
                logger.info("Processed %s ingestion document(s)", processed)
            if event_settings.backend != "redis":
                await asyncio.sleep(1)
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

"""Durable, KB-scoped RAG chat conversation persistence (BL-012).

Chat conversations and their message history are persisted across the API and
worker containers via a
:class:`~conversations.adapters.protocols.ConversationRepository` (in-memory for
tests/dev, Postgres for production) — replacing the previously seeded,
in-memory-only ``ApiState`` conversation store.
"""

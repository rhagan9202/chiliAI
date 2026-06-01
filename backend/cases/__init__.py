"""Durable, KB-scoped case management (BL-010).

Investigation cases are promoted from alerts and persisted across the API and
worker containers via a :class:`~cases.adapters.protocols.CaseRepository`
(in-memory for tests/dev, Postgres for production).
"""

"""Backend-internal developer/demo utilities, run inside the worker container.

Distinct from the repo-root ``tools/`` package (host-side demo/data-prep
scripts driven over HTTP against a running API). Modules here need direct
access to the worker's own runtime dependencies — the active domain
config, the object store, and the Redis Streams event bus — so they are
invoked as ``python -m tools.<name>`` *inside* the ``worker`` container
(``docker compose exec worker python -m tools.<name> ...``), where those
services are reachable exactly as they are for ``agent.coordinator``.
"""

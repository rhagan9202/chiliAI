# tools package — developer utilities for sample data generation and demo setup.
#
# Typechecked via this directory's own pyrightconfig.json (see
# .github/workflows/ci.yml's "Type-check tools/" step), not folded into
# backend/pyproject.toml's [tool.pyright]. The split originated when a
# since-deleted backend/tools/ package (removed 2026-07-24 with the demo
# analytics trigger, analytics.34) shared the bare top-level name "tools";
# pyright resolves a given dotted module name to one filesystem location per
# Program, so a single invocation reaching both directories made every
# `import tools` resolve to whichever one won program-wide (verified
# empirically against pyright 1.1.409). Kept as-is for isolation:
# two separate invocations, two separate Programs, each with an
# unambiguous "tools".

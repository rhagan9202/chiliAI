# tools package — developer utilities for sample data generation and demo setup.
#
# Typechecked via this directory's own pyrightconfig.json (see
# .github/workflows/ci.yml's "Type-check tools/" step), not folded into
# backend/pyproject.toml's [tool.pyright]. backend/tools/ (see
# backend/tools/demo_trigger_analytics.py) is an unrelated package that also
# uses the bare top-level name "tools"; pyright resolves a given dotted
# module name to one filesystem location per Program, so a single invocation
# reaching both directories makes every `import tools` in that run resolve
# to whichever one wins program-wide, not resolvable via a
# per-execution-environment override (verified empirically against pyright
# 1.1.409). Two separate invocations, two separate Programs, each with an
# unambiguous "tools".

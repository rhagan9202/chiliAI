# analytics/identity_resolution

Deterministic identity resolution (SAFE-CMS-012): score how likely a source
entity and a set of canonical candidates are the same real-world identity,
persist the scored pairings as identity links, and let a data steward approve,
reject or split each link. Scoring is rule-based — weighted property matches,
no model — so the same inputs always produce the same score and reasons.

See the package-level guide, [`../README.md`](../README.md), for shared
analytics conventions.

## Layout

| File | Responsibility |
|------|----------------|
| `models.py` | Request/result models (`IdentityResolutionRequest`, `IdentityCandidateEntity`, `IdentityCandidateScore`, `IdentityMatchReason`, `IdentityResolutionResult`), the durable `IdentityLinkRecord` with `IdentityLinkDecisionRecord` history, `IdentityLinkRepositoryQuery` / `IdentityLinkPage`, `IdentityLinkDecisionRequest`, `IdentityRelationshipProjectionRequest`, and the `IdentityMatchConfidence` / `IdentityReviewState` / `IdentityLinkReviewState` / `IdentityLinkDecision` literals. |
| `service.py` | `IdentityResolutionService` — `score_candidates`, `materialize_link_records`, `project_identity_relationships`. |
| `repository.py` | `IdentityLinkRepository` protocol (`upsert_link`, `get_link`, `list_links`), `InMemoryIdentityLinkRepository`, and `IdentityDecisionService` (`record_decision`). |
| `adapters/postgres.py` | `PostgresIdentityLinkRepository` over `database.ConnectionProvider`. |

## Contracts and invariants

- **Scoring.** Each configured field that matches adds a fixed weight:
  natural-key fields 0.55 (exact match), identifier fields 0.30 and address
  fields 0.15 (normalized match; addresses expand common street
  abbreviations). The score is capped at 1.0, and candidates scoring 0 are
  dropped. Results are sorted by score descending, then entity id.
- **KB scoping.** Candidates whose `knowledge_base_id` differs from the
  request's are never scored; their ids come back in
  `excluded_candidate_ids`.
- **Bands.** Score >= 0.85 is `high` / `auto_linkable`; >= 0.50 is `medium` /
  `steward_review`; anything lower is `low` / `needs_review`.
- **Link identity.** A link id is derived from (KB, canonical entity, source
  entity), so re-scoring the same pair targets the same row.
- **Steward decisions.** `record_decision` appends to `decision_history` and
  moves `review_state` to `merged` (`approve_merge`), `rejected`
  (`reject_merge`) or `split` (`split_identity`). An unknown link raises
  `KeyError`. When the dependencies are wired, it publishes
  `IdentityLinkDecisionRecordedEvent` and writes an `identity_link.<decision>`
  audit event through `auditlog.service.AuditLogService`.
- **Cross-module imports.** `repository.py` imports `auditlog.models` and
  `auditlog.service` directly, rather than reaching them through a protocol.

## How it is reached

API only (`api/routers/identity.py`, prefix `/identity`); no worker handler
calls this module.

| Route | Role | Behaviour |
|-------|------|-----------|
| `POST /identity/resolve-candidates` | analyst | `score_candidates`, then `materialize_link_records` and `IdentityLinkRepository.upsert_link` for each scored pair. A link that already has steward decision history is left untouched; an existing link without history keeps its `created_at`. This preserve-on-rescore logic lives in the router. |
| `GET /identity/canonical/{entity_id}` | viewer | Pages `list_links` for one canonical entity. |
| `POST /identity/links/{link_id}/decision` | analyst | `IdentityDecisionService.record_decision`; 404 for an unknown link. |

All three return 404 when the caller's `knowledge_base_ids` scope does not
include the requested KB. `get_identity_link_repository` in
`api/dependencies.py` selects Postgres when a connection provider is
configured and the in-memory repository otherwise.

## Persistence

`identity_links` — migration `0018_identity_links`, primary key
`(knowledge_base_id, id)`, with jsonb `source_refs`, `match_reasons` and
`decision_history` and CHECK constraints on `confidence`, `score` and
`review_state`.

`delete_by_kb` is the `identity_links` step of the KB-delete cascade
(`knowledgebases/cleanup.py`).

## Current gaps (verified in code)

- `IdentityLinkDecisionRecordedEvent` (`identity.link_decision.recorded`) has
  no consumer, so steward decisions do not reach the graph or other read
  models (see [`docs/ledger/event-catalog.md`](../../../docs/ledger/event-catalog.md)).
- `project_identity_relationships` turns scored candidates into graph
  `Relationship`s, but nothing outside the tests calls it. Projecting links
  into the graph is left to the caller.

## Tests

`tests/analytics/test_identity_resolution_service.py`,
`tests/analytics/test_identity_resolution_repository.py`,
`tests/analytics/test_identity_resolution_postgres.py`, and
`tests/api/test_identity_router.py`.

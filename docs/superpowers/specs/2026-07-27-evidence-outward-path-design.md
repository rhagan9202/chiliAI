# Evidence pack: attach to a case, export — Design (UXA-405)

> Status: **Approved** (2026-07-27) · Issue: [#66](https://github.com/rhagan9202/chiliAI/issues/66) · Epic: [#72](https://github.com/rhagan9202/chiliAI/issues/72) · Tracker: [#73](https://github.com/rhagan9202/chiliAI/issues/73)

## 1. Problem and current state

Most of UXA-405 shipped in `68bfb4a`: the narrative is typeset as the primary content, the pack carries its generation time, source documents and humanized score labels, the promote toast links to the case it created, and the alert reflects promotion and refuses a second one.

Two items were left open because they needed product decisions:

1. **"Attach to case"** — the evidence pack has no outward path. The only way evidence reaches a case is `POST /cases/promote`, which creates a *new* case from an alert. There is no way to add anything to an **existing** case.
2. **Export** — the pack cannot leave the browser. The ticket says "print/PDF/permalink".

### 1.1 What the model supports today

- `Case.alert_ids: list[str]` — plural, but only ever written once, by `promote_from_alert`.
- `Case.evidence_pack_id: str | None` — singular, set from the promoting alert's pack.
- `CaseService` has `create`, `get`, `list`, `update`, `add_feedback`, `promote_from_alert`. Nothing appends to an existing case.
- Evidence packs are owned by `analytics/explainability/` (service + repository) and exposed read-only via `GET /evidence-packs/{id}` (`api/routers/evidence.py`).
- The product's only export today is scorecards: `GET /scorecards/runs/{id}/export?format=json|markdown` returning `{run_id, format, content}`, downloaded client-side by a local `downloadTextFile` helper in `ScorecardRunPage.tsx`. There is no PDF machinery anywhere in the repo.

## 2. Decisions

| # | Decision | Choice | Why |
|---|---|---|---|
| D-1 | What "attach" means | **Add this alert to an existing case** | It is the workflow promote cannot express: "I already have a case, this belongs to it." The duplicate-promotion guard already keys off `alert_ids`, so it composes without new state. |
| D-2 | `evidence_pack_id` on attach | **Left untouched** | It records what the case came *from*. Repointing it on every attach would silently rewrite the case's origin; the attached alert's own pack stays reachable through the alert. |
| D-3 | Export formats | **JSON + Markdown, matching scorecards** | One export idiom in the product, not two. Markdown pastes into a case note or a report; JSON stays machine-readable. Print/PDF was considered and dropped: it produces nothing machine-readable and the subgraph canvas prints poorly. |
| D-4 | Where the export is rendered | **Server-side, in `analytics/explainability/`** | That module owns evidence packs, and `api/` holds no business logic (architecture hard rule 1). One renderer means the file an analyst downloads cannot drift from what another caller gets. |
| D-5 | When the export is rendered | **On demand, not stored** | Scorecard exports are persisted because they are generated during a run. An evidence pack is already durable and the render is deterministic from it, so storing a second copy would only create a staleness question. |
| D-6 | Cross-case exclusivity | **Not enforced** | An alert already in another case is filtered out by the UI, exactly as it already is for promote. Making exclusivity a backend invariant would have to change promote too, which is a wider decision than this ticket. Recorded as a follow-up. |

## 3. Design

### 3.1 Backend — attach an alert to a case

```
POST /cases/{case_id}/alerts        require_role("analyst")
body: CaseAttachAlertRequest { alert_id: str, notes: str | None }
->    CaseDetailResponse            (same shape every other case mutation returns)
```

`CaseService.attach_alert(*, knowledge_base_id, case_id, alert, notes=None) -> Case`:

- Raises `CaseNotFoundError` when the case is absent or belongs to another KB → 404.
- Raises `AlertAlreadyAttachedError` when `alert.id` is already in `case.alert_ids` → 409, mirroring `PolicyItemAlreadyTriagedError`'s treatment and the ticket's "promoting twice is not possible".
- Otherwise appends the id, appends a `CaseTimelineEvent(occurred_at=utc_now(), label="Alert attached", detail=...)` naming the alert and any note, bumps `updated_at`, and persists through `repository.update`.
- Never writes `evidence_pack_id` (D-2).

**Interface:** given a case and an alert, the case grows by exactly one alert and one timeline entry, or the call fails. No partial state.

### 3.2 Backend — evidence pack export

```
GET /evidence-packs/{id}/export?knowledge_base_id=&format=json|markdown
->  EvidencePackExportResponse { evidence_pack_id, format, filename, content }
    require_role("viewer")   # same gate as reading the pack
```

`filename` is server-chosen (`evidence-<id>.md` / `.json`) so the download name is one decision in one place rather than reconstructed by every caller.

The renderer lives in `analytics/explainability/` as a pure function over the stored pack:

```python
def render_evidence_markdown(pack: EvidencePack, *, alert_title: str | None = None) -> str: ...
```

Markdown contains, in order: title, generated timestamp, confidence, humanized scores, the narrative sections, attribution, contributing items, source documents, and the subgraph node/edge ids. JSON is the pack payload as stored — stable and machine-readable.

Score keys are humanized with the same rule the viewer uses (`peer_deviation` → `Peer deviation`); the frontend's `humanizeScoreName` and this renderer must agree, and a test asserts the shared cases.

### 3.3 Frontend

- **`downloadTextFile` moves** from `ScorecardRunPage.tsx` to `src/utils/downloadFile.ts`. Two consumers now; one implementation.
- **`EvidencePackViewer` gains an optional `actions?: ReactNode`** region rendered beside the pack header. It stays presentational: it does not know what a case is.
- **Alert Feed** supplies *Attach to case* and *Export*. **Investigation Workbench** supplies *Export* only — there is no alert in hand there, and attaching one would mean inventing it.
- **Attach** opens a picker listing open cases in the KB, excluding any whose `alert_ids` already contain this alert. With no eligible case it renders an empty state pointing at promote, which is how the first case gets created.
- **Export** offers JSON and Markdown, disabled while a request is in flight, matching the scorecard viewer's affordance.

## 4. Error handling

| Case | Behavior |
|---|---|
| Attach to an unknown case, or one in another KB | 404; the picker only lists this KB's cases, so this is a stale-UI path |
| Attach an alert already on that case | 409; the picker excludes those cases, so likewise |
| Attach request fails | Error toast; the case list is not mutated optimistically |
| Export of an unknown pack | 404 |
| Export request fails | Error toast; no partial file is written (the blob is only created on success) |
| Pack with no narrative sections | Markdown still renders header, scores and subgraph; empty sections are omitted rather than rendered as empty headings |

## 5. Testing

**Backend**
- `attach_alert`: appends the id and a timeline event; leaves `evidence_pack_id` untouched; 404 unknown case; 409 duplicate; KB isolation.
- Router: happy path returns the updated `CaseDetailResponse`; role gating.
- `render_evidence_markdown`: full pack; pack with empty narrative/attribution/sources; score humanization matches the frontend's rule.
- Export route: both formats, `filename` shape, 404.

**Frontend unit**
- `downloadFile`: builds and revokes the object URL.
- Viewer renders the actions region only when given one.
- Attach picker: excludes cases already holding the alert; empty state when none are eligible.
- Export buttons request the right format and hand the content to the download helper.

**E2E** (`e2e/promote-to-case.spec.ts` or a new `evidence-outward-path.spec.ts`) against the live stack: attach the seeded alert to the seeded case through the real API, assert it appears in the case's alerts and timeline; download the Markdown export and assert it contains the narrative and the pack id.

## 6. Out of scope

- **One-case exclusivity for alerts** (D-6) — would have to change promote too. Follow-up on #66.
- **PDF and print stylesheets** (D-3).
- **A permalink route for an evidence pack.** There is no route that opens a pack directly today; adding one is a routing decision beyond this ticket.
- **Multi-evidence cases** (`evidence_pack_ids`) — considered and rejected in D-2; it would leave a confusing singular alongside a plural.

# monitoring

Threshold-driven **active monitoring**: evaluates streamed observations
against per-metric thresholds, generates `Alert`s, and persists the durable,
KB-scoped `alert_history` audit log the API's alert feed reads from.

## Layout

| File | Responsibility |
|------|----------------|
| `models.py` | `MonitoringObservation`, `MonitoringBatch`, `AlertCandidate`, `AlertGroup`, `AlertHistoryRecord`, `AlertTriageEvent`, `SuppressionRule`. |
| `lifecycle.py` | `ALERT_TRANSITIONS` state machine and `validate_alert_transition` — the single source of truth both adapters call before writing a status change. |
| `protocols.py` | `MonitoringServiceProtocol`. |
| `adapters/protocols.py` | `ObservationSourceProtocol`, `ObservationWriter`, `AlertHistoryWriter`, `AlertFeedStoreProtocol` (list/get/acknowledge/assign/transition_status/count/delete), `AlertRepositoryProtocol`. |
| `adapters/in_memory.py` | `InMemoryObservationSource`, `InMemoryObservationWriter`, `InMemoryAlertRepository`, `InMemoryAlertHistoryWriter` (dict-backed `AlertFeedStoreProtocol` for tests/dev). |
| `adapters/postgres.py` | `PostgresObservationSource`/`PostgresObservationStore` over the `observations` hypertable; `PostgresAlertHistoryStore` over `alert_history`. |
| `service.py` | `MonitoringService` — threshold evaluation, dedup, rate-limiting, suppression rules, alert grouping, and the higher-level acknowledge/resolve/transition operations used by `analytics`/`api` call sites that work through `AlertRepositoryProtocol` rather than the durable feed store directly. |
| `exceptions.py` | `MonitoringError`, `MonitoringConfigurationError`, `MonitoringSourceError`, `AlertNotFoundError`, `AlertAlreadyResolvedError`, `AlertLifecycleError`, `AlertConcurrentModificationError`. |

## Contract: a lost write race is typed, not a generic source error

`AlertFeedStoreProtocol.acknowledge` and `.transition_status` are read
(current status) → validate (`validate_alert_transition`) → write, against a
row two callers can race on: two analysts triaging the same alert, or two
requests hitting the same row through `get_alert_feed_store`
(`api/dependencies.py`), which is an `lru_cache(maxsize=1)` **process
singleton shared across every threadpool request** — the race is reachable
in production, not just in a test with a widened window.

Before this task (`monitoring.22`), a lost race and a genuine persistence
failure were the same exception (`MonitoringSourceError`, distinguished only
by message text), and the in-memory adapter had no guard at all — two
concurrent writers could both pass validation against the same stale status
and both write, the second silently discarding the first's transition (and
its own `from_status` audit claim going stale with it). No caller anywhere
converted either into a 409, so every path — including the bulk endpoint,
which aborted the whole batch specifically *because* the error was
untypeable and could equally mean the database was down — surfaced an opaque
500.

**What raises `AlertConcurrentModificationError` now:**

- `PostgresAlertHistoryStore.acknowledge` / `.transition_status`: the guarded
  `UPDATE ... WHERE status = %s` affects 0 rows (someone else committed
  first). The store re-reads the row and re-validates the caller's original
  target status against what is actually there: if the transition is now
  forbidden, `AlertLifecycleError` propagates (the real problem is the
  lifecycle, not the race); if it is still valid — including "someone else
  already landed exactly the transition I wanted" — the miss is purely a
  lost race and this is raised.
- `InMemoryAlertHistoryWriter.acknowledge` / `.transition_status`: reproduces
  the same two-step shape without a database. Each method captures the
  row's status via an unguarded read, then re-checks it against the live
  value under a `threading.Lock` held across the re-check-and-write; on a
  mismatch it applies the identical re-validate-then-decide logic described
  above. Both adapters are proven under a **deliberately widened**
  compare-to-write window (a `threading.Barrier` plus a monkeypatched,
  delayed `validate_alert_transition`, mirroring
  `InMemoryCaseRepository.update`'s fix in the previous sprint) rather than
  relying on lucky GIL scheduling — see
  `tests/monitoring/test_alert_history_writer.py` and the concurrent tests
  in `tests/monitoring/test_postgres_alert_history.py`.

**What it means to a caller:** always safe to retry — reload the alert and
resubmit. This is the load-bearing distinction from `MonitoringSourceError`,
which means the underlying store itself is unavailable or errored and is
*not* safe to retry blindly. A caller that only ever sees
`MonitoringSourceError` cannot tell "retry me" from "the database is down";
that conflation is exactly what made the bulk endpoint abort on either.

**Gateway mapping** (`api/dependencies.py`):

- `build_alert_acknowledge_payload` / `build_alert_status_update_payload`
  (single-alert routes) catch `AlertConcurrentModificationError` and raise
  `HTTPException(409)`, the same treatment `AlertLifecycleError` already
  got.
- `build_alert_bulk_status_update_payload` (`POST /alerts/bulk/status`)
  catches it as a **per-row skip** (`AlertBulkRejection(reason=
  "concurrent_modification")`) and continues the batch, rather than
  aborting. This is a deliberate behavior change from the pre-`monitoring.22`
  abort-on-any-`MonitoringSourceError` path: nothing is committed on the
  lost-race branch (both adapters raise *before* writing), so skipping is
  safe, and there is no reason one caller's bad luck on a shared row should
  cost every other alert in the batch its update. A genuine
  `MonitoringSourceError` — the database is actually down — still aborts the
  whole batch as a 500; that is not a case where "the rest of the batch
  would probably be fine anyway" is a safe assumption.

## Design decision: a shared base, not a fourth bespoke type

`cases` already has its own `CaseConcurrentModificationError` (mirrored
`in_memory`/`postgres` CAS, no gateway 409 mapping). Before this task,
`monitoring` had *no* typed answer at all. Rather than give `monitoring` a
second, unrelated bespoke type, `AlertConcurrentModificationError` inherits
from **both**:

```python
class AlertConcurrentModificationError(MonitoringError, ConcurrentModificationError):
    ...
```

- `MonitoringError` — so module-internal and test code keeps catching it the
  same way every other monitoring exception is caught, consistent with
  `cases`' own module-scoped hierarchy.
- `shared.exceptions.ConcurrentModificationError` — a new cross-module
  marker base (`shared/exceptions.py`, alongside the pre-existing
  `ConfigurationError`, which is already used the same way from
  `api/dependencies.py`). It is not raised directly.

  **What this buys today, honestly stated:** nothing catches
  `ConcurrentModificationError` yet. The gateway mapping described above
  catches `AlertConcurrentModificationError` by its own name, not by the
  shared base, and `AlertConcurrentModificationError` is currently the
  *only* subclass in the tree — `CaseConcurrentModificationError` has not
  been retrofitted onto it (see "Known gap" below). The marker is a bet
  that Task 3's `conversations` module will add its own subclass, at which
  point a single `except ConcurrentModificationError` becomes possible
  somewhere that needs "was this any module's lost race" without importing
  every module's exception module — a good bet, and the reason the base
  exists now rather than being added later, but a capability to *finish*,
  not one already delivered. Nothing in this codebase relies on it being
  shared yet.

**Why not a purely shared type with no per-module subclass?** The three
permitted cross-module interaction paths (`api/`, `agent/`, `shared/`;
`docs/architecture.md` "Hard Rules" §1) restrict *business-logic*
communication, not exception ownership, and every other module in this
codebase (`cases`, `conversations`, ...) keeps its own `exceptions.py` with
its own hierarchy. Losing `MonitoringError`-ness would mean any code that
`except MonitoringError` to catch "something in this module's exception
family went wrong" would silently stop catching lost races — a regression
this task should not introduce for the sake of the shared vocabulary.

**Why not leave it purely per-module, matching `cases` as-is?** The next
task in this sprint (`conversations`) needs the identical contract, and a
third independently-invented bespoke type would be the fourth answer to one
question (the three being: `cases`' own type, `monitoring`'s old
message-text-only overload of `MonitoringSourceError`, and no answer at
all). A shared marker base costs nothing extra to define now, and defining
it here — rather than after a second module needs it — means Task 3 can
adopt an existing contract instead of inventing (or retrofitting) one. It
does not, by itself, give anything a single type to look for yet; see
above.

**Known gap:** `cases.exceptions.CaseConcurrentModificationError` predates
`ConcurrentModificationError` and has **not** been retrofitted to inherit
from it — that would touch `cases/`, which is out of this task's scope.
This is why the shared base currently has exactly one subscriber
(`AlertConcurrentModificationError`), not several — treat the gap as a
follow-up, not as a sign the design is wrong; `conversations` (Task 3) is
the base's intended second subscriber.

## The contract for `conversations` (and any future module)

1. Define your own `<Module>ConcurrentModificationError` in your module's
   `exceptions.py`, inheriting from **both** your module's base error type
   and `shared.exceptions.ConcurrentModificationError`.
2. Give it a message that says the object changed concurrently and that the
   caller should reload and retry — this is a "retry me" signal, not a
   diagnostic to log and swallow.
3. Guard the in-memory adapter's read-validate-write with a `threading.Lock`
   held across the re-check-and-write (see `InMemoryAlertHistoryWriter`
   above, or `InMemoryCaseRepository.update` for the simpler
   externally-supplied-CAS-token variant). Prove it with a test that
   **deliberately widens** the compare-to-write window (patch/wrap so a
   sleep sits between the compare and the write, or synchronize two threads
   on a `threading.Barrier`) rather than relying on GIL scheduling to
   surface the race.
4. Prove the Postgres adapter's `WHERE <version-column> = %s` guarded write
   the same way, with a real concurrent-writer test (see
   `test_concurrent_acknowledge_loses_instead_of_committing_over_a_dismissal`
   and its "signals retry not forbidden" sibling in
   `tests/monitoring/test_postgres_alert_history.py`) — not just the
   in-memory adapter. Adapter parity is a test requirement, not a nice-to-
   have: an untested adapter is an unguarded one.
5. Map it to `HTTPException(409)` at the routes/dependency-builder layer
   that owns your module's API surface, and decide deliberately (and write
   down the decision) whether any bulk/batch caller should skip-and-continue
   on it rather than abort — safe exactly when nothing commits on the
   lost-race branch, as is true here.

## Tests

- `tests/monitoring/test_alert_history_writer.py` — `InMemoryAlertHistoryWriter`
  CRUD, KB scoping, lifecycle validation, and the two concurrency guard
  tests (forbidden-after-race silently landing → must raise
  `AlertLifecycleError`; same-target race → must raise
  `AlertConcurrentModificationError`, not double-write), each run under a
  deliberately widened compare-to-write window.
- `tests/monitoring/test_postgres_alert_history.py` — `@pytest.mark.integration`
  (skipped without `DATABASE_URL`); the same two concurrency scenarios
  against the real CAS-guarded `UPDATE`, using a `threading.Barrier`-
  synchronized monkeypatch of `validate_alert_transition` to force the
  interleave deterministically.
- `tests/api/test_alerts_router.py` — the single-alert route's 409 mapping,
  and the bulk endpoint's per-row-skip-not-abort behavior on a lost race
  (contrasted with its still-abort-as-500 behavior on a genuine
  `MonitoringSourceError`, and its audit-on-every-committed-transition
  invariant even when a later row in the batch fails).

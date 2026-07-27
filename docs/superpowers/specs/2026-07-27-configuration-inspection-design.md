# Configuration page: schema browser, field-level validation, transport warning — Design (UXA-404)

> Status: **Approved** (2026-07-27) · Issue: [#65](https://github.com/rhagan9202/chiliAI/issues/65) · Epic: [#72](https://github.com/rhagan9202/chiliAI/issues/72) · Tracker: [#73](https://github.com/rhagan9202/chiliAI/issues/73)

## 1. Problem and current state

`/configuration` used to be a read-only stat dump. Most of UXA-404 shipped in `6b3a563`: every count now opens to the items behind it via `ExpandableCount`, and the pack switcher and active-pack editor (admin-gated, mirroring `require_role("admin")` on `/config/packs|validate|apply|switch`) were already in place.

Three items were left open, and this design covers exactly those:

1. **`/config/domain/schema` is rendered as a count, not a reference.** `ExpandableCount` lists the 27 top-level property *names*. The payload also carries 50 `$defs` with types, enums, defaults and descriptions — the material an operator needs when hand-writing a pack — and none of it is reachable.
2. **Validation errors are not shown against the offending field.** `ActivePackEditor` renders a list under the editor: each issue shows its dotted `field` path, message and `error_type`. The backend already returns `loc: list[str]` alongside `field`. Nothing connects an issue to the line that caused it.
3. **The event-transport constraint is invisible.** `api/routers/config.py` documents that packs must not change the event transport across a hot-swap, but nothing enforces or surfaces it.

### 1.1 What actually happens on a transport-changing swap

Traced through the code rather than the docstring:

1. `_capture_pre_swap_event_bus` publishes `config.updated` on the **pre-swap** transport — deliberately, because that is the one the worker is still consuming.
2. The worker receives it and calls `build_worker_dependencies()`, which re-reads the now-active config and builds a **new event bus on the new transport**.
3. The worker rebinds and converges.

So the reload signal is not stranded. What breaks is narrower:

- **Queued work is abandoned.** Anything pending or unacked on the old stream or consumer group has no consumer after the rebind. In-flight ingestion and analytics jobs stop, silently.
- **Failure is invisible.** If the new transport is unreachable, `build_worker_dependencies()` raises; the worker deliberately keeps its previous dependencies ("never leave the worker deps-less") and logs `CONFIG RELOAD FAILED`. The API serves the new pack, the worker serves the old one, and nothing in the UI says so.

### 1.2 The live footgun (found while designing)

Resolved through the real loader:

| Pack | `events.backend` | `uri` |
|---|---|---|
| `medicare_fraud` | **`in_memory`** | `None` |
| `medicare_fraud_cms_desynpuf` (active) | `redis` | `redis://redis:6379` |
| `food_supply_chain` | `redis` | `redis://redis:6379` |
| `department_air_force_housing` | `redis` | `redis://redis:6379` |

`medicare_fraud.yaml` carries no `events:` block, so `DomainConfig` fills it with `EventBusConfig()` defaults, which is `in_memory`. The API and worker are **separate processes**, so each builds its own in-process bus: the API publishes events nothing consumes, with no error anywhere. Switching to that pack from the UI kills the pipeline silently, today.

This is why the candidate's transport must be resolved **server-side**. Comparing raw YAML client-side would read an omitted `events:` block as "unchanged" — precisely backwards.

## 2. Decisions

| # | Decision | Choice | Why |
|---|---|---|---|
| D-1 | Transport change on hot-swap | **Warn before confirm; never refuse** | A deliberate transport migration stays possible (drain the queue, then swap). Refusing turns a rare-but-legitimate operation into a wall, and would need `/config/validate` to depend on the *active* pack, changing what that endpoint means. |
| D-2 | `in_memory` as swap target | **Warn harder, still allow** | Consistent with D-1, and the base pack is genuinely usable in a single-process run. The wording states the specific consequence rather than generic "transport changed". |
| D-3 | Where the candidate's transport is resolved | **Server-side, on existing responses** | An omitted `events:` block resolves to defaults only through the loader. See §1.2. |
| D-4 | Schema browser depth | **Section → fields, drill into nested `$defs` on demand** | Answers "what goes under `ingestion`?" and "what values does `events.backend` take?" without rendering 50 defs at once. |
| D-5 | "Against the offending field" | **Click an issue to jump to and select its line** | Keeps the existing accessible list as the primary surface; adds the connection the ticket asks for. Gutter diagnostics were considered and dropped: hover text is not keyboard-reachable without extra work, for the same information. |
| D-6 | `medicare_fraud.yaml`'s missing `events:` block | **Not changed here** | Fixing the pack would hide the general problem: any user-supplied pack can omit the block. Recorded as a follow-up on #65. |

## 3. Design

### 3.1 Backend — resolved transport on existing responses

Additive only. No new endpoint, no behavior change, no new failure path.

```python
class PackTransport(BaseModel):
    """Resolved event transport for a pack (defaults applied by the loader)."""
    backend: str
    uri: str | None = None
    stream_prefix: str
    consumer_group: str
```

- `PackSummary` gains `transport: PackTransport | None` — `None` when the pack fails to load, since there is nothing to resolve.
- `ValidatePackResponse` gains the same field, populated when `valid` is true. This is the editor's path: inline `content` goes through the same loader, so an omitted `events:` block resolves identically.
- `_summarize_pack` fills it from the `pack_config` it already loads; the validate handler from the config it already builds. Neither loads anything extra.

**Interface:** given a pack reference or inline content, the API answers "what transport would this pack run on?" Callers need no knowledge of `EventBusConfig` defaults.

### 3.2 Frontend — transport warning

`useDomainConfig()` already returns the active resolved `events`, so the comparison is local once the candidate's transport is in hand.

A pure module `src/components/config/transportDelta.ts`:

```ts
export interface TransportDelta {
  changes: Array<{ field: string; from: string; to: string }>
  severity: 'none' | 'changed' | 'decoupled'
}
export function transportDelta(
  active: EventBusConfig | null | undefined,
  candidate: PackTransport | null | undefined,
): TransportDelta
```

- Compares `backend`, `uri`, `stream_prefix`, `consumer_group`.
- `severity: 'decoupled'` when either side is `in_memory` and they differ — the API and worker land on separate in-process buses.
- `severity: 'none'` when nothing differs, or when either input is absent (an unknown transport is not a claim of change).

Rendered by:

- **`PackSwitcher`** — in the confirm step, above *Confirm switch*, so it is read before the irreversible click.
- **`ActivePackEditor`** — beside *Apply*, after a successful validate.

Copy states the delta (`backend: redis → in_memory`) and the consequence: queued worker jobs on the current stream are abandoned; for `decoupled`, that the API and worker end up on separate in-process buses and the pipeline stops.

### 3.3 Frontend — schema browser

`src/components/config/schemaModel.ts` (pure, no React):

```ts
export interface SchemaField {
  name: string
  type: string          // rendered form: "string", "array of EntityConfig", "one of: redis, in_memory"
  required: boolean
  description?: string
  defaultValue?: unknown
  ref?: string          // $defs key when this field expands further
}
export function sectionFields(schema: JsonSchema, sectionName: string): SchemaField[]
export function defFields(schema: JsonSchema, defKey: string, seen: ReadonlySet<string>): SchemaField[]
```

- `$ref` resolution is on demand and one level per expansion, carrying a `seen` set so a self-referential definition cannot recurse forever.
- Enum and `Literal` types render as their allowed values, which is the question an operator actually has.

`SchemaBrowser.tsx` replaces the "Schema sections" `ExpandableCount`: the 27 sections, each expanding to its fields; a field with a `ref` expands inline. Read-only.

### 3.4 Frontend — jump to the offending line

`packYaml.ts` gains:

```ts
export function locateInYaml(text: string, loc: readonly string[]): { from: number; to: number } | null
```

- Uses `parseDocument` from the `yaml` package (already a dependency) and the node's `.range`, which is `[start, valueEnd, nodeEnd]` in character offsets. Verified against the installed version: `getIn(['entities', 0, 'name'], true).range` returns `[38, 46, 47]`.
- `loc` arrives as strings. `getIn` accepts string indices into sequences (`'0'` works as well as `0`), so the path passes through unchanged — no per-segment coercion.
- Returns `null` for an empty `loc` (file-level parse errors) or a path that does not exist in the current buffer, where `getIn` returns `undefined`. The buffer may have been edited since validation, so this is a normal case, not an error.

`YamlEditor` gains an `onReady?: (view: EditorView) => void` prop, forwarded to `@uiw/react-codemirror`'s `onCreateEditor(view, state)` (confirmed present in the installed `index.d.ts`), so `ActivePackEditor` can dispatch a selection and scroll it into view.

Each issue renders as a `<button>` when its `loc` resolves against the current buffer, and as the current plain text when it does not. The existing `data-testid="validation-issues"` and `.config-manager__issue-field` hooks are preserved — `e2e/config-manager.spec.ts` already asserts them.

## 4. Error handling

| Case | Behavior |
|---|---|
| Pack fails to load | `transport: null`; no warning rendered (unknown ≠ changed). The row already shows its validation error. |
| Active config unavailable | No warning; nothing to compare against. |
| `loc` empty or unresolvable in the current buffer | Issue renders as plain text, not a button. No dead control. |
| Schema payload missing or malformed | Browser renders the existing empty hint, as `ExpandableCount` does today. |
| Self-referential `$def` | `seen` set stops expansion and the field renders as a terminal type. |

## 5. Testing

**Backend**
- `_summarize_pack` projects the resolved transport, including a pack with **no `events:` block** resolving to `in_memory` — the §1.2 case, asserted directly.
- `transport: null` for an unloadable pack.
- `/config/validate` returns the transport for inline content whose `events:` block is omitted.

**Frontend unit**
- `transportDelta`: identical, one-field change, `decoupled` in both directions, absent inputs.
- `schemaModel`: section fields, `$ref` resolution, enum rendering, cycle guard.
- `locateInYaml`: nested mapping path, sequence index, unresolvable path, empty `loc`.
- `PackSwitcher` / `ActivePackEditor`: warning renders with the delta; issue buttons appear only for resolvable paths.

**E2E** — `e2e/config-manager.spec.ts` already covers the switch round-trip and validate-error rendering, and **both tests currently skip** because the dev session is `viewer` (`CHILI_DEV_ANONYMOUS_ROLE=viewer` on the API container) while the pack routes require `admin`. Getting them to run is part of this work, not incidental: set `CHILI_DEV_ANONYMOUS_ROLE=admin` and restart the API, then extend the spec to assert the transport warning and the jump-to-line behavior against the real validator.

> Recreating the API container re-resolves `${CHILI_DEV_ANONYMOUS_ROLE:-viewer}` and `${CHILI_CONFIG_PATH:-…}` from the current shell, silently dropping values set elsewhere. Capture `docker exec chiliai-api-1 printenv | grep CHILI` before restarting and re-export explicitly.

## 6. Out of scope

- Pinning `events:` in `medicare_fraud.yaml` (D-6) — follow-up on #65.
- Any refusal path in `/config/apply|switch` (D-1).
- Editing packs on disk. The editor's buffer remains browser-local; Apply re-reads from disk, as its own copy already states.
- Detecting after the fact that the worker failed to converge. Worth having, needs a worker→API health signal that does not exist, and belongs with observability rather than here.

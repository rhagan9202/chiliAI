# Shared Types Contract

**Verified against codebase:** 2026-07-23
**Source:** `backend/shared/types.py`, `backend/shared/protocols.py`

These are the generic platform types. No domain-specific types (`Provider`, `Claim`, etc.) live here — those are configured via `DomainConfig` and flow at runtime as generic `Entity` instances.

---

## Config-definition types (`shared/types.py`)

### `PropertyType` (enum)

```python
class PropertyType(str, enum.Enum):
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    DATE = "date"
    LIST = "list"
    BOOLEAN = "boolean"
    ENUM = "enum"
    NESTED = "nested"
```

### `PropertyDefinition`

```python
class PropertyDefinition(BaseModel):
    type: PropertyType
    display: str
    required: bool = False
    enum_values: list[str] | None = None
    min_value: float | None = None
    max_value: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
```

### `EntityDefinition`

```python
class EntityDefinition(BaseModel):
    name: str
    display_label: str
    icon: str
    natural_key: list[str] = []   # property names that uniquely identify an instance;
                                   # used by LlmDocumentExtractor for intra-chunk dedup
    properties: dict[str, PropertyDefinition]
```

### `RelationshipDefinition`

```python
class RelationshipDefinition(BaseModel):
    name: str
    display_label: str
    source: str   # must match an EntityDefinition.name
    target: str   # must match an EntityDefinition.name
```

---

## Generic runtime types

### `Entity`

```python
class Entity(BaseModel):
    id: str
    type: str                              # matches EntityDefinition.name
    properties: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    created_at: datetime                   # default: utc_now()
    updated_at: datetime | None = None
    version: int = 1
```

### `Relationship`

```python
class Relationship(BaseModel):
    id: str
    type: str                              # matches RelationshipDefinition.name
    source_id: str
    target_id: str
    properties: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    created_at: datetime                   # default: utc_now()
    updated_at: datetime | None = None
    version: int = 1
    weight: float | None = None
```

### `Alert`

```python
class Alert(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    severity: str                          # TODO: SeverityLevel enum pending
    title: str
    reasoning: str
    evidence_pack_id: str | None = None
    created_at: datetime
    status: Literal["open","acknowledged","investigating","resolved","dismissed"] = "open"
    updated_at: datetime | None = None
    acknowledged: bool = False             # deprecated in favor of status
    resolved_by: str | None = None
    resolution_notes: str | None = None
```

### `FeatureAttribution`

```python
class FeatureAttribution(BaseModel):
    feature_name: str
    contribution: float                    # signed, model-space
    rationale: str = ""
```

### `EvidenceNarrativeSection`

```python
class EvidenceNarrativeSection(BaseModel):
    heading: str
    body: str
    evidence_refs: list[str] = []
```

### `EvidencePack`

```python
class EvidencePack(BaseModel):
    id: str
    alert_id: str
    reasoning: str
    subgraph_nodes: list[str]
    subgraph_edges: list[str]
    confidence: float
    created_at: datetime                   # default: utc_now()
    scores: dict[str, float] = {}
    source_documents: list[str] = []
    attribution: list[FeatureAttribution] = []          # B3 (BL-048): SHAP or noop, per-feature signed contributions
    narrative_sections: list[EvidenceNarrativeSection] = []  # B3 (BL-048): LLM or deterministic narrative, grouped by heading
```

Both new fields default to `[]` so pre-B3 persisted object-store packs deserialize unchanged (`EvidencePack.model_validate` on a legacy payload with neither key present).

### `KnowledgeBase`

```python
class KnowledgeBase(BaseModel):
    id: str
    name: str
    description: str
    entity_count: int = 0
    relationship_count: int = 0
    document_count: int = 0
    status: Literal["active","building","ready","error","archived"] = "active"
    created_at: datetime
    updated_at: datetime | None = None
    pending_cleanup: bool = False
```

### `MonitoringObservation`

```python
class MonitoringObservation(BaseModel):
    entity_id: str
    entity_type: str
    metric_name: str
    score: float                           # [0.0, 1.0]
    observed_at: datetime                  # default: utc_now()
    rationale: str
    evidence_pack_id: str | None = None
```

---

## Validation helpers

### `validate_entity`

```python
def validate_entity(
    entity: Entity,
    entity_definitions: list[EntityDefinition],
) -> list[str]:
```
Returns list of error strings (empty = valid). Checks: type recognized, required properties present, no unknown properties, type constraints (enum values, numeric ranges, string length, pattern).

### `validate_relationship`

```python
def validate_relationship(
    relationship: Relationship,
    relationship_definitions: list[RelationshipDefinition],
    entities_by_id: dict[str, Entity],
) -> list[str]:
```
Checks: relationship type recognized, source/target entities resolved and match declared types.

---

## Cross-cutting protocols (`shared/protocols.py`)

### `ObjectStoreProtocol`

```python
class ObjectStoreProtocol(Protocol):
    def put_bytes(self, key: str, content: bytes, *, media_type: str | None = None, metadata: dict[str, object] | None = None) -> StoredObjectWriteResult: ...
    def get_bytes(self, key: str) -> StoredObject: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def list_keys(self, prefix: str) -> list[str]: ...
```

`storage/protocols.py` re-exports this as `ObjectStore = ObjectStoreProtocol`.

### `StoredObjectWriteResult`

```python
class StoredObjectWriteResult(BaseModel):
    key: str
    size_bytes: int   # >= 0
    media_type: str | None = None
    metadata: dict[str, object] = {}
```

### `StoredObject`

```python
class StoredObject(BaseModel):
    key: str
    content: bytes
    size_bytes: int   # >= 0
    media_type: str | None = None
    metadata: dict[str, object] = {}
```

### `Configurable`

```python
class Configurable(Protocol):
    def configure(self, config: DomainConfig) -> None: ...
```

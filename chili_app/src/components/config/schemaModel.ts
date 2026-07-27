/**
 * Project the domain-pack JSON Schema into something an operator can read
 * (UXA-404).
 *
 * `/config/domain/schema` is Pydantic's `model_json_schema()`: 27 top-level
 * properties and 50 `$defs`, wired together with `$ref`. The Configuration page
 * used to render the property *names* and stop there, which answers no question
 * anyone has. What an operator writing a pack asks is "what goes under
 * `ingestion`?" and "what values does `events.backend` take?" — so a section
 * resolves to its fields, and a field whose type is a definition expands into
 * that definition on demand.
 *
 * Resolution is one level per expansion, never eager: expanding all 50 defs
 * up front would produce a wall, and the schema is cyclic in places.
 */

export type JsonSchema = Record<string, unknown>

export interface SchemaField {
  name: string
  /** Rendered type: "string", "array of EntityDefinition", "one of: redis, in_memory". */
  type: string
  required: boolean
  description?: string
  /** Present only when the schema declares one; `null` is a real default. */
  defaultValue?: unknown
  hasDefault: boolean
  /** `$defs` key this field expands into, when it has one. */
  ref?: string
}

const DEFS_PREFIX = '#/$defs/'

function asRecord(value: unknown): JsonSchema | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as JsonSchema)
    : null
}

function refName(node: JsonSchema): string | undefined {
  const ref = node['$ref']
  return typeof ref === 'string' && ref.startsWith(DEFS_PREFIX)
    ? ref.slice(DEFS_PREFIX.length)
    : undefined
}

/**
 * Pydantic renders an optional field as `anyOf: [T, null]`. That is a nullability
 * detail, not a type an operator needs to read, so unwrap to the non-null branch.
 */
function unwrapNullable(node: JsonSchema): JsonSchema {
  const anyOf = node['anyOf']
  if (!Array.isArray(anyOf)) {
    return node
  }
  const branches = anyOf.map(asRecord).filter((entry): entry is JsonSchema => entry !== null)
  const meaningful = branches.filter((entry) => entry['type'] !== 'null')
  return meaningful.length === 1 && meaningful[0] ? { ...meaningful[0] } : node
}

function describeType(node: JsonSchema): string {
  const enumValues = node['enum']
  if (Array.isArray(enumValues) && enumValues.length > 0) {
    return `one of: ${enumValues.map((value) => String(value)).join(', ')}`
  }

  const ref = refName(node)
  if (ref) {
    return ref
  }

  const type = node['type']
  if (type === 'array') {
    const items = asRecord(node['items'])
    if (items) {
      const itemsUnwrapped = unwrapNullable(items)
      return `array of ${describeType(itemsUnwrapped)}`
    }
    return 'array'
  }
  if (type === 'object') {
    const additional = asRecord(node['additionalProperties'])
    return additional ? `map of ${describeType(unwrapNullable(additional))}` : 'object'
  }
  if (typeof type === 'string') {
    return type
  }
  // anyOf with several meaningful branches, or an unconstrained field.
  const anyOf = node['anyOf']
  if (Array.isArray(anyOf)) {
    const rendered = anyOf
      .map(asRecord)
      .filter((entry): entry is JsonSchema => entry !== null)
      .filter((entry) => entry['type'] !== 'null')
      .map((entry) => describeType(entry))
    if (rendered.length > 0) {
      return rendered.join(' or ')
    }
  }
  return 'any'
}

/**
 * The `$defs` key a field expands into: either the field itself or, for a list,
 * its item type. Enums are terminal — their values are already on screen.
 */
function expandableRef(node: JsonSchema): string | undefined {
  if (Array.isArray(node['enum'])) {
    return undefined
  }
  const direct = refName(node)
  if (direct) {
    return direct
  }
  const items = asRecord(node['items'])
  return items ? refName(unwrapNullable(items)) : undefined
}

function toField(name: string, raw: JsonSchema, required: Set<string>): SchemaField {
  const node = unwrapNullable(raw)
  const description = node['description'] ?? raw['description']
  const ref = expandableRef(node)
  const hasDefault = 'default' in raw || 'default' in node
  const field: SchemaField = {
    name,
    type: describeType(node),
    required: required.has(name),
    hasDefault,
  }
  if (typeof description === 'string' && description !== '') {
    field.description = description
  }
  if (hasDefault) {
    field.defaultValue = 'default' in raw ? raw['default'] : node['default']
  }
  if (ref) {
    field.ref = ref
  }
  return field
}

function fieldsOf(node: JsonSchema | null): SchemaField[] {
  if (!node) {
    return []
  }
  const properties = asRecord(node['properties'])
  if (!properties) {
    return []
  }
  const requiredList = node['required']
  const required = new Set(
    Array.isArray(requiredList) ? requiredList.filter((v): v is string => typeof v === 'string') : [],
  )
  return Object.entries(properties)
    .map(([name, raw]) => {
      const child = asRecord(raw)
      return child ? toField(name, child, required) : null
    })
    .filter((field): field is SchemaField => field !== null)
}

/** Top-level section names, in schema order. */
export function sectionNames(schema: JsonSchema | null | undefined): string[] {
  const properties = schema ? asRecord(schema['properties']) : null
  return properties ? Object.keys(properties) : []
}

/**
 * The `$defs` key a top-level section resolves through, if any.
 *
 * The section is already showing that definition's fields, so it counts as
 * open: without seeding the guard with it, a self-referential definition
 * (`EntityDefinition.children` is an `EntityDefinition`) expands one extra
 * time before the guard notices.
 */
export function sectionRef(
  schema: JsonSchema | null | undefined,
  sectionName: string,
): string | undefined {
  if (!schema) {
    return undefined
  }
  const properties = asRecord(schema['properties'])
  const raw = properties ? asRecord(properties[sectionName]) : null
  return raw ? expandableRef(unwrapNullable(raw)) : undefined
}

/** Fields of one top-level section, resolving through a `$ref` when it has one. */
export function sectionFields(
  schema: JsonSchema | null | undefined,
  sectionName: string,
): SchemaField[] {
  if (!schema) {
    return []
  }
  const properties = asRecord(schema['properties'])
  const raw = properties ? asRecord(properties[sectionName]) : null
  if (!raw) {
    return []
  }
  const node = unwrapNullable(raw)
  const ref = expandableRef(node)
  if (ref) {
    return defFields(schema, ref)
  }
  return fieldsOf(node)
}

/** Fields of one `$defs` entry. Returns [] for an unknown key. */
export function defFields(
  schema: JsonSchema | null | undefined,
  defKey: string,
): SchemaField[] {
  if (!schema) {
    return []
  }
  const defs = asRecord(schema['$defs'])
  return fieldsOf(defs ? asRecord(defs[defKey]) : null)
}

/**
 * Whether a field can be expanded here, given the definitions already open
 * above it. The schema is cyclic in places, so an ancestor that is open again
 * would recurse forever.
 */
export function canExpand(field: SchemaField, openDefs: ReadonlySet<string>): boolean {
  return field.ref !== undefined && !openDefs.has(field.ref)
}

/** One-line summary of a section for the collapsed row. */
export function sectionSummary(fields: readonly SchemaField[]): string {
  if (fields.length === 0) {
    return 'no documented fields'
  }
  const requiredCount = fields.filter((field) => field.required).length
  return requiredCount > 0
    ? `${fields.length} fields · ${requiredCount} required`
    : `${fields.length} fields`
}

import {
  canExpand,
  defFields,
  sectionFields,
  sectionNames,
  sectionRef,
  sectionSummary,
  type JsonSchema,
  type SchemaField,
} from './schemaModel'
import './configManager.css'

interface SchemaBrowserProps {
  schema: JsonSchema | null | undefined
}

/**
 * Browsable reference for the domain-pack schema (UXA-404).
 *
 * The page reported "Schema sections 27" and, once expanded, the 27 property
 * *names* — which answers nothing an operator writing a pack actually asks.
 * Each section now opens to its fields, and a field whose type is a definition
 * opens into that definition, resolved only when asked: the payload carries 50
 * of them and the schema is cyclic in places.
 *
 * Built from nested `<details>` for the same reason `ExpandableCount` is: the
 * page stays scannable and every level is reachable without a modal.
 */
export function SchemaBrowser({ schema }: SchemaBrowserProps) {
  const sections = sectionNames(schema)

  return (
    <details className="config-count" data-testid="schema-browser">
      <summary className="config-count__summary">
        <span className="metric-row__label">Schema sections</span>
        <strong>{sections.length}</strong>
      </summary>
      {sections.length === 0 ? (
        <p className="page-copy-block">The pack schema is unavailable.</p>
      ) : (
        <ul className="schema-browser__sections">
          {sections.map((section) => {
            // The section already displays this definition's fields, so it is
            // open: seeding the guard here is what stops a self-referential
            // definition expanding one extra time.
            const resolvedThrough = sectionRef(schema, section)
            return (
              <li key={section}>
                <SchemaNode
                  fields={sectionFields(schema, section)}
                  name={section}
                  openDefs={new Set(resolvedThrough ? [resolvedThrough] : [])}
                  schema={schema}
                />
              </li>
            )
          })}
        </ul>
      )}
    </details>
  )
}

interface SchemaNodeProps {
  name: string
  fields: SchemaField[]
  schema: JsonSchema | null | undefined
  /** Definitions already open above this node — the cycle guard. */
  openDefs: ReadonlySet<string>
}

function SchemaNode({ name, fields, schema, openDefs }: SchemaNodeProps) {
  return (
    <details className="schema-browser__node">
      <summary className="schema-browser__node-summary">
        <code>{name}</code>
        <span className="metric-row__label">{sectionSummary(fields)}</span>
      </summary>
      {fields.length === 0 ? (
        <p className="page-copy-block">
          This section takes free-form values; the pack schema documents no fields for it.
        </p>
      ) : (
        <ul className="schema-browser__fields">
          {fields.map((field) => (
            <li className="schema-browser__field" key={field.name}>
              <div className="schema-browser__field-head">
                <code className="schema-browser__field-name">{field.name}</code>
                <span className="schema-browser__field-type">{field.type}</span>
                {field.required ? (
                  <span className="schema-browser__field-required">required</span>
                ) : field.hasDefault ? (
                  <span className="metric-row__label">
                    default {formatDefault(field.defaultValue)}
                  </span>
                ) : null}
              </div>
              {field.description ? (
                <p className="schema-browser__field-description">{field.description}</p>
              ) : null}
              {field.ref !== undefined ? (
                canExpand(field, openDefs) ? (
                  <SchemaNode
                    fields={defFields(schema, field.ref)}
                    name={field.ref}
                    openDefs={new Set([...openDefs, field.ref])}
                    schema={schema}
                  />
                ) : (
                  // Already open further up: expanding again would recurse
                  // forever, and the fields are on screen anyway.
                  <p className="metric-row__label">
                    Repeats <code>{field.ref}</code>, shown above.
                  </p>
                )
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </details>
  )
}

function formatDefault(value: unknown): string {
  if (value === null) return 'none'
  if (typeof value === 'string') return value === '' ? 'empty' : value
  if (Array.isArray(value)) return value.length === 0 ? 'empty list' : JSON.stringify(value)
  if (typeof value === 'object') {
    return Object.keys(value as object).length === 0 ? 'empty' : JSON.stringify(value)
  }
  return String(value)
}

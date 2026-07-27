import type {
  DomainConfig,
  DomainPropertyDefinition,
  RuntimeEntity,
} from '../api/contracts'

/** One property row on an entity dossier, ready to render. */
export interface EntityPropertyView {
  key: string
  /** `PropertyDefinition.display` from the active pack, else a humanized key. */
  label: string
  /** Formatted for the declared `PropertyType`. */
  value: string
  /** Shown before the reader expands the full list. */
  featured: boolean
}

type PropertyType = DomainPropertyDefinition['type']

/** How many properties lead the list when the pack declares no chip fields. */
const DEFAULT_FEATURED_COUNT = 4

// Fixed locale and UTC so a dossier reads the same for every analyst looking at
// the same record, and so a date-only value is never shifted across midnight.
const DATE_FORMAT = new Intl.DateTimeFormat('en-US', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
})
const INTEGER_FORMAT = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })
const DECIMAL_FORMAT = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/
// Deliberately strict: `new Date()` happily reads "sometime in 2020" as
// 1 Jan 2020, which would present a guess as a fact.
const ISO_TIMESTAMP = /^\d{4}-\d{2}-\d{2}[T ]/

function formatDate(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const dateOnly = DATE_ONLY.exec(value)
  if (dateOnly) {
    const [, year, month, day] = dateOnly
    return DATE_FORMAT.format(new Date(Date.UTC(Number(year), Number(month) - 1, Number(day))))
  }
  if (!ISO_TIMESTAMP.test(value)) return null
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : DATE_FORMAT.format(parsed)
}

/** Renders a raw property value according to its configured type. */
export function formatPropertyValue(value: unknown, type: PropertyType | undefined): string {
  if (value === null || value === undefined) return ''

  switch (type) {
    case 'date':
      // An unparseable date is still information; show it rather than "Invalid Date".
      return formatDate(value) ?? stringify(value)
    case 'integer':
      return typeof value === 'number' ? INTEGER_FORMAT.format(value) : stringify(value)
    case 'decimal':
      return typeof value === 'number' ? DECIMAL_FORMAT.format(value) : stringify(value)
    case 'boolean':
      return typeof value === 'boolean' ? (value ? 'Yes' : 'No') : stringify(value)
    default:
      return stringify(value)
  }
}

function stringify(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => stringify(item)).join(', ')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

/** `legacy_source_file` → `Legacy source file`, for keys the pack does not declare. */
function humanize(key: string): string {
  const words = key.replace(/[_-]+/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/**
 * Turns an entity's raw property bag into labeled, ordered, formatted rows.
 *
 * Order follows the pack's declaration order — the order a domain author chose
 * — with anything the pack does not describe appended. The title and subtitle
 * fields are dropped because the dossier header already renders them; without
 * that, the identifying field would appear twice and crowd out the rest.
 */
export function getEntityProperties(
  entity: RuntimeEntity,
  config: DomainConfig,
): EntityPropertyView[] {
  const definitions =
    config.entities.find((candidate) => candidate.name === entity.type)?.properties ?? {}
  const displayFields = config.ui?.display_fields?.[entity.type]
  const headerFields = new Set(
    [displayFields?.title, displayFields?.subtitle].filter(
      (field): field is string => typeof field === 'string',
    ),
  )
  const chipFields = displayFields?.chips ?? []

  const declared = Object.keys(definitions)
  const undeclared = Object.keys(entity.properties).filter((key) => !(key in definitions))

  const rows: Omit<EntityPropertyView, 'featured'>[] = []
  for (const key of [...declared, ...undeclared]) {
    if (headerFields.has(key)) continue
    const value = formatPropertyValue(entity.properties[key], definitions[key]?.type)
    if (value === '') continue
    rows.push({ key, label: definitions[key]?.display ?? humanize(key), value })
  }

  const featured =
    chipFields.length > 0
      ? new Set(chipFields)
      : new Set(rows.slice(0, DEFAULT_FEATURED_COUNT).map((row) => row.key))

  return rows.map((row) => ({ ...row, featured: featured.has(row.key) }))
}

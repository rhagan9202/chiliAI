import { describe, expect, it } from 'vitest'

import {
  canExpand,
  defFields,
  sectionFields,
  sectionNames,
  sectionRef,
  sectionSummary,
  type JsonSchema,
} from '../schemaModel'

/** Shapes taken from the real `/config/domain/schema` payload. */
const SCHEMA: JsonSchema = {
  title: 'DomainConfig',
  type: 'object',
  required: ['domain', 'entities'],
  properties: {
    schema_version: { title: 'Schema Version', type: 'string' },
    domain: { $ref: '#/$defs/DomainInfo' },
    entities: { items: { $ref: '#/$defs/EntityDefinition' }, title: 'Entities', type: 'array' },
    events: { anyOf: [{ $ref: '#/$defs/EventBusConfig' }, { type: 'null' }], default: null },
    labels: { additionalProperties: { type: 'string' }, type: 'object', title: 'Labels' },
  },
  $defs: {
    DomainInfo: {
      type: 'object',
      required: ['name'],
      properties: {
        name: { type: 'string', title: 'Name', description: 'Machine name.' },
        display_name: { anyOf: [{ type: 'string' }, { type: 'null' }], default: null },
      },
    },
    EntityDefinition: {
      type: 'object',
      required: ['name'],
      properties: {
        name: { type: 'string', title: 'Name' },
        children: { items: { $ref: '#/$defs/EntityDefinition' }, type: 'array' },
      },
    },
    EventBusConfig: {
      type: 'object',
      properties: {
        backend: {
          default: 'in_memory',
          enum: ['redis', 'in_memory'],
          title: 'Backend',
          type: 'string',
        },
        stream_maxlen: { anyOf: [{ type: 'integer' }, { type: 'null' }], default: null },
      },
    },
  },
}

describe('sectionNames', () => {
  it('lists the top-level sections in schema order', () => {
    expect(sectionNames(SCHEMA)).toEqual([
      'schema_version',
      'domain',
      'entities',
      'events',
      'labels',
    ])
  })

  it('survives a missing schema', () => {
    expect(sectionNames(null)).toEqual([])
    expect(sectionNames({})).toEqual([])
  })
})

describe('sectionFields', () => {
  it('resolves a section that is a $ref into that definition', () => {
    const fields = sectionFields(SCHEMA, 'domain')

    expect(fields.map((field) => field.name)).toEqual(['name', 'display_name'])
    expect(fields[0]).toMatchObject({
      type: 'string',
      required: true,
      description: 'Machine name.',
    })
  })

  it('resolves a list section into its item definition', () => {
    // "what goes in an entities entry" is the question, not "it is an array".
    expect(sectionFields(SCHEMA, 'entities').map((field) => field.name)).toEqual([
      'name',
      'children',
    ])
  })

  it('unwraps an optional section to the type an operator writes', () => {
    // anyOf: [EventBusConfig, null] is a nullability detail.
    expect(sectionFields(SCHEMA, 'events').map((field) => field.name)).toEqual([
      'backend',
      'stream_maxlen',
    ])
  })

  it('returns nothing for an unknown section', () => {
    expect(sectionFields(SCHEMA, 'nope')).toEqual([])
  })
})

describe('field rendering', () => {
  it('renders an enum as its allowed values', () => {
    const [backend] = defFields(SCHEMA, 'EventBusConfig')

    expect(backend?.type).toBe('one of: redis, in_memory')
    expect(backend?.hasDefault).toBe(true)
    expect(backend?.defaultValue).toBe('in_memory')
  })

  it('renders a list of definitions by its item type', () => {
    const children = defFields(SCHEMA, 'EntityDefinition').find((f) => f.name === 'children')

    expect(children?.type).toBe('array of EntityDefinition')
    expect(children?.ref).toBe('EntityDefinition')
  })

  it('renders a map by its value type', () => {
    const labels = sectionFields(SCHEMA, 'labels')
    // labels has no properties of its own; it is a bare map.
    expect(labels).toEqual([])
  })

  it('marks a null default as present rather than missing', () => {
    const maxlen = defFields(SCHEMA, 'EventBusConfig').find((f) => f.name === 'stream_maxlen')

    expect(maxlen?.hasDefault).toBe(true)
    expect(maxlen?.defaultValue).toBeNull()
    expect(maxlen?.type).toBe('integer')
  })

  it('does not offer to expand an enum', () => {
    const [backend] = defFields(SCHEMA, 'EventBusConfig')

    expect(backend?.ref).toBeUndefined()
  })
})

describe('sectionRef', () => {
  it('reports the definition a section resolves through', () => {
    expect(sectionRef(SCHEMA, 'domain')).toBe('DomainInfo')
    expect(sectionRef(SCHEMA, 'entities')).toBe('EntityDefinition')
    expect(sectionRef(SCHEMA, 'events')).toBe('EventBusConfig')
  })

  it('reports nothing for a section with no definition behind it', () => {
    expect(sectionRef(SCHEMA, 'schema_version')).toBeUndefined()
    expect(sectionRef(SCHEMA, 'nope')).toBeUndefined()
    expect(sectionRef(null, 'domain')).toBeUndefined()
  })
})

describe('canExpand', () => {
  it('allows expanding a definition that is not already open', () => {
    const children = defFields(SCHEMA, 'EntityDefinition').find((f) => f.name === 'children')!

    expect(canExpand(children, new Set())).toBe(true)
  })

  it('refuses to reopen a definition already above it', () => {
    // EntityDefinition.children is EntityDefinition; without the guard this
    // expands forever.
    const children = defFields(SCHEMA, 'EntityDefinition').find((f) => f.name === 'children')!

    expect(canExpand(children, new Set(['EntityDefinition']))).toBe(false)
  })

  it('refuses a field with no definition behind it', () => {
    const [name] = defFields(SCHEMA, 'DomainInfo')

    expect(canExpand(name!, new Set())).toBe(false)
  })
})

describe('sectionSummary', () => {
  it('counts fields and required ones', () => {
    expect(sectionSummary(sectionFields(SCHEMA, 'domain'))).toBe('2 fields · 1 required')
  })

  it('omits the required clause when there are none', () => {
    expect(sectionSummary(defFields(SCHEMA, 'EventBusConfig'))).toBe('2 fields')
  })

  it('says so when a section documents nothing', () => {
    expect(sectionSummary([])).toBe('no documented fields')
  })
})

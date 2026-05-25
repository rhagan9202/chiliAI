import { describe, expect, it } from 'vitest'

import { parseCsvRecords, parseJsonlRecords } from '../parseRecords'

describe('record preview parsers', () => {
  it('parses CSV rows into objects using the header row', () => {
    const result = parseCsvRecords(
      'claim_id,provider_npi,billed_amount\nc1,1234567890,99.50\n',
    )

    expect(result.rows).toEqual([
      { claim_id: 'c1', provider_npi: '1234567890', billed_amount: '99.50' },
    ])
    expect(result.errors).toEqual([])
  })

  it('keeps commas and doubled quotes inside quoted CSV fields', () => {
    const result = parseCsvRecords('claim_id,note\nc1,"office, ""outpatient"""\n')

    expect(result.rows[0]).toEqual({ claim_id: 'c1', note: 'office, "outpatient"' })
  })

  it('keeps newlines inside quoted CSV fields', () => {
    const result = parseCsvRecords('claim_id,note\nc1,"line one\nline two"\nc2,single line\n')

    expect(result.rows).toEqual([
      { claim_id: 'c1', note: 'line one\nline two' },
      { claim_id: 'c2', note: 'single line' },
    ])
    expect(result.errors).toEqual([])
  })

  it('reports empty CSV content', () => {
    const result = parseCsvRecords('\n\n')

    expect(result.rows).toEqual([])
    expect(result.errors[0]).toMatchObject({
      source: 'client',
      severity: 'error',
      message: 'CSV content is empty.',
    })
  })

  it('reports malformed CSV quotes', () => {
    const result = parseCsvRecords('claim_id,note\nc1,"unterminated\n')

    expect(result.rows).toEqual([])
    expect(result.errors[0].message).toContain('Unterminated quoted field')
  })

  it('parses one JSON object per JSONL line', () => {
    const result = parseJsonlRecords('{"claim_id":"c1"}\n{"claim_id":"c2"}\n')

    expect(result.rows).toEqual([{ claim_id: 'c1' }, { claim_id: 'c2' }])
    expect(result.errors).toEqual([])
  })

  it('reports empty JSONL content', () => {
    const result = parseJsonlRecords('\n\n')

    expect(result.rows).toEqual([])
    expect(result.errors[0]).toMatchObject({
      source: 'client',
      severity: 'error',
      message: 'JSONL content is empty.',
    })
  })

  it('reports invalid JSONL lines and returns no rows', () => {
    const result = parseJsonlRecords('{"claim_id":"c1"}\nnot-json\n')

    expect(result.rows).toEqual([])
    expect(result.errors[0]).toMatchObject({
      rowIndex: 1,
      source: 'client',
      severity: 'error',
    })
  })

  it('reports non-object JSONL lines', () => {
    const result = parseJsonlRecords('["not", "object"]\n')

    expect(result.rows).toEqual([])
    expect(result.errors[0]).toMatchObject({
      rowIndex: 0,
      source: 'client',
      severity: 'error',
    })
  })
})

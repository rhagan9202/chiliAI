import { describe, expect, it } from 'vitest'

import type { RecordFeedConfig, ValidationConfig } from '../../../api/contracts'
import {
  isValidDateValue,
  validateDocumentFiles,
  validateRecordFile,
  validateRecordRows,
  validateRequiredWizardState,
} from '../validateIngestion'

const feed: RecordFeedConfig = {
  name: 'claims_feed',
  record_type: 'claim_record',
  source: 'file_upload',
  id_field: 'claim_id',
  record_schema: {
    claim_id: { type: 'string', display: 'Claim ID', required: true },
    provider_npi: {
      type: 'string',
      display: 'Provider NPI',
      required: true,
      pattern: '^[0-9]{10}$',
    },
    billed_amount: { type: 'decimal', display: 'Billed Amount', required: true },
    line_count: { type: 'integer', display: 'Line Count' },
    paid: { type: 'boolean', display: 'Paid' },
    service_date: { type: 'date', display: 'Date of Service', required: true },
    anomaly_score: { type: 'decimal', display: 'Anomaly Score', required: true },
  },
  entities: [],
  relationships: [],
  observations: [],
}

const validationConfig: ValidationConfig = {
  max_file_size_mb: 1,
  allowed_content_types: ['text/csv', 'application/json'],
  max_query_length: 10000,
  max_rag_question_length: 5000,
}

describe('ingestion validation', () => {
  it('requires selected knowledge base and source type', () => {
    const issues = validateRequiredWizardState({
      knowledgeBaseId: null,
      sourceType: null,
      feedName: null,
    })

    expect(issues.map((issue) => issue.message)).toEqual([
      'Select a knowledge base before submitting.',
      'Choose Documents or Structured Records before submitting.',
    ])
    expect(issues.every((issue) => issue.kind === 'prerequisite')).toBe(true)
  })

  it('requires feed name only for structured records', () => {
    expect(
      validateRequiredWizardState({
        knowledgeBaseId: 'kb-1',
        sourceType: 'documents',
        feedName: null,
      }),
    ).toEqual([])

    expect(
      validateRequiredWizardState({
        knowledgeBaseId: 'kb-1',
        sourceType: 'records',
        feedName: null,
      }),
    ).toMatchObject([{ id: 'missing-feed', severity: 'error', source: 'client', kind: 'prerequisite' }])
  })

  it('tags empty-collection issues as prerequisites and leaves other content issues untagged', () => {
    // Empty collections → prerequisite kind (user just hasn't uploaded yet)
    const noFiles = validateDocumentFiles([], validationConfig)
    expect(noFiles).toMatchObject([{ id: 'missing-files', kind: 'prerequisite' }])

    const noRecordFile = validateRecordFile(null)
    expect(noRecordFile).toMatchObject([{ id: 'missing-record-file', kind: 'prerequisite' }])

    const noRows = validateRecordRows(feed, [])
    expect(noRows).toMatchObject([{ id: 'missing-records', kind: 'prerequisite' }])

    // Actual bad content (wrong type, oversized file, row pattern mismatch) → untagged
    const badFile = new File(['x'], 'claims.exe', { type: 'application/x-msdownload' })
    Object.defineProperty(badFile, 'size', { value: 2 * 1024 * 1024 })
    const fileIssues = validateDocumentFiles([badFile], validationConfig)
    expect(fileIssues.length).toBeGreaterThan(0)
    expect(fileIssues.every((issue) => issue.kind === undefined)).toBe(true)

    const badRow = validateRecordRows(feed, [
      {
        claim_id: 'c1',
        provider_npi: 'not-numeric',
        billed_amount: 'not-money',
        service_date: '2026-01-15',
        anomaly_score: '0.8',
      },
    ])
    expect(badRow.length).toBeGreaterThan(0)
    expect(badRow.every((issue) => issue.kind === undefined)).toBe(true)
  })

  it('requires document files', () => {
    const issues = validateDocumentFiles([], validationConfig)

    expect(issues).toMatchObject([
      {
        id: 'missing-files',
        source: 'client',
        severity: 'error',
      },
    ])
  })

  it('validates document content type and size', () => {
    const file = new File(['x'], 'claims.exe', { type: 'application/x-msdownload' })
    Object.defineProperty(file, 'size', { value: 2 * 1024 * 1024 })

    const issues = validateDocumentFiles([file], validationConfig)

    expect(issues.map((issue) => issue.message)).toContain(
      'claims.exe uses unsupported content type application/x-msdownload.',
    )
    expect(issues.map((issue) => issue.message)).toContain(
      'claims.exe exceeds the configured 1 MB file limit.',
    )
  })

  it('rejects empty document files before upload', () => {
    const file = new File([''], 'empty.json', { type: 'application/json' })

    const issues = validateDocumentFiles([file], validationConfig)

    expect(issues).toMatchObject([
      {
        id: 'empty-empty.json',
        severity: 'error',
        message: 'empty.json is empty.',
      },
    ])
  })

  it('validates records upload files', () => {
    expect(validateRecordFile(null)).toMatchObject([
      { id: 'missing-record-file', severity: 'error' },
    ])

    const empty = new File([''], 'claims.csv', { type: 'text/csv' })
    expect(validateRecordFile(empty)).toMatchObject([
      { id: 'empty-record-file', message: 'claims.csv is empty.' },
    ])

    const unsupported = new File(['hello'], 'claims.exe', {
      type: 'application/x-msdownload',
    })
    expect(validateRecordFile(unsupported)).toMatchObject([
      {
        id: 'unsupported-record-file',
        message: 'claims.exe must be a CSV or JSONL records file.',
      },
    ])
  })

  it('warns for large document files when no max file size is configured', () => {
    const file = new File(['x'], 'large.pdf', { type: 'application/pdf' })
    Object.defineProperty(file, 'size', { value: 51 * 1024 * 1024 })

    const issues = validateDocumentFiles([file], null)

    expect(issues).toMatchObject([
      {
        severity: 'warning',
        message: 'large.pdf is larger than 50 MB; backend limits may reject it.',
      },
    ])
  })

  it('requires record rows', () => {
    const issues = validateRecordRows(feed, [])

    expect(issues).toMatchObject([
      {
        id: 'missing-records',
        source: 'client',
        severity: 'error',
      },
    ])
  })

  it('validates required record fields and primitive coercion', () => {
    const issues = validateRecordRows(feed, [
      {
        claim_id: '',
        provider_npi: '12345',
        billed_amount: 'not-money',
        line_count: '1.5',
        paid: 'maybe',
        service_date: 'not-a-date',
        anomaly_score: '0.8',
      },
    ])

    expect(issues.map((issue) => issue.message)).toEqual([
      'Row 1 is missing required field Claim ID.',
      'Row 1 field Provider NPI does not match ^[0-9]{10}$.',
      'Row 1 field Billed Amount must be a decimal number.',
      'Row 1 field Line Count must be an integer.',
      'Row 1 field Paid must be a boolean.',
      'Row 1 field Date of Service must be a valid date.',
    ])
  })

  it('rejects typed JSONL values that are invalid for numeric fields', () => {
    const issues = validateRecordRows(feed, [
      {
        claim_id: 'c1',
        provider_npi: '1234567890',
        billed_amount: false,
        line_count: [],
        service_date: '2026-01-15',
        anomaly_score: {},
      },
      {
        claim_id: 'c2',
        provider_npi: '1234567890',
        billed_amount: '   ',
        line_count: true,
        service_date: '2026-01-15',
        anomaly_score: 0.4,
      },
    ])

    expect(issues.map((issue) => issue.message)).toEqual([
      'Row 1 field Billed Amount must be a decimal number.',
      'Row 1 field Line Count must be an integer.',
      'Row 1 field Anomaly Score must be a decimal number.',
      'Row 2 field Billed Amount must be a decimal number.',
      'Row 2 field Line Count must be an integer.',
    ])
  })

  it('validates enum values and numeric bounds from record schema', () => {
    const boundedFeed: RecordFeedConfig = {
      ...feed,
      record_schema: {
        ...feed.record_schema,
        claim_type: {
          type: 'enum',
          display: 'Claim Type',
          required: true,
          enum_values: ['inpatient', 'outpatient'],
        },
        anomaly_score: {
          type: 'decimal',
          display: 'Anomaly Score',
          required: true,
          min_value: 0,
          max_value: 1,
        },
      },
    }

    const issues = validateRecordRows(boundedFeed, [
      {
        claim_id: 'c1',
        provider_npi: '1234567890',
        billed_amount: '99.50',
        service_date: '2026-01-15',
        anomaly_score: '1.5',
        claim_type: 'other',
      },
    ])

    expect(issues.map((issue) => issue.message)).toEqual([
      'Row 1 field Anomaly Score must be <= 1.',
      'Row 1 field Claim Type must be one of inpatient, outpatient.',
    ])
  })

  it('validates string min and max length from record schema', () => {
    const lengthFeed: RecordFeedConfig = {
      ...feed,
      record_schema: {
        ...feed.record_schema,
        claim_id: {
          type: 'string',
          display: 'Claim ID',
          required: true,
          min_length: 3,
          max_length: 6,
        },
      },
    }

    expect(
      validateRecordRows(lengthFeed, [
        {
          claim_id: 'c',
          provider_npi: '1234567890',
          billed_amount: '1',
          service_date: '2026-01-15',
          anomaly_score: '0.1',
        },
      ]),
    ).toMatchObject([
      { message: 'Row 1 field Claim ID must have length >= 3.' },
    ])

    expect(
      validateRecordRows(lengthFeed, [
        {
          claim_id: 'claim-100',
          provider_npi: '1234567890',
          billed_amount: '1',
          service_date: '2026-01-15',
          anomaly_score: '0.1',
        },
      ]),
    ).toMatchObject([
      { message: 'Row 1 field Claim ID must have length <= 6.' },
    ])
  })

  it('does not add numeric bound issues when integer coercion fails', () => {
    const boundedIntegerFeed: RecordFeedConfig = {
      ...feed,
      record_schema: {
        ...feed.record_schema,
        line_count: {
          type: 'integer',
          display: 'Line Count',
          min_value: 2,
        },
      },
    }

    const issues = validateRecordRows(boundedIntegerFeed, [
      {
        claim_id: 'c1',
        provider_npi: '1234567890',
        billed_amount: '99.50',
        line_count: '1.5',
        service_date: '2026-01-15',
        anomaly_score: '0.1',
      },
    ])

    expect(issues.map((issue) => issue.message)).toEqual([
      'Row 1 field Line Count must be an integer.',
    ])
  })

  it('does not add length issues for values with the wrong declared shape', () => {
    const lengthFeed: RecordFeedConfig = {
      ...feed,
      record_schema: {
        ...feed.record_schema,
        tags: {
          type: 'list',
          display: 'Tags',
          max_length: 2,
        },
        details: {
          type: 'nested',
          display: 'Details',
          max_length: 1,
        },
      },
    }

    const issues = validateRecordRows(lengthFeed, [
      {
        claim_id: 'c1',
        provider_npi: '1234567890',
        billed_amount: '99.50',
        service_date: '2026-01-15',
        anomaly_score: '0.1',
        tags: 'not-a-list',
        details: ['not', 'nested'],
      },
    ])

    expect(issues).toEqual([])
  })

  it('matches string patterns against the full field value', () => {
    const patternFeed: RecordFeedConfig = {
      ...feed,
      record_schema: {
        ...feed.record_schema,
        provider_npi: {
          type: 'string',
          display: 'Provider NPI',
          required: true,
          pattern: '\\d{10}',
        },
      },
    }

    const issues = validateRecordRows(patternFeed, [
      {
        claim_id: 'c1',
        provider_npi: 'abc1234567890xyz',
        billed_amount: '99.50',
        service_date: '2026-01-15',
        anomaly_score: '0.8',
      },
    ])

    expect(issues.map((issue) => issue.message)).toEqual([
      'Row 1 field Provider NPI does not match \\d{10}.',
    ])
  })

  it('passes valid record rows', () => {
    const issues = validateRecordRows(feed, [
      {
        claim_id: 'c1',
        provider_npi: '1234567890',
        billed_amount: '99.50',
        line_count: '2',
        paid: 'true',
        service_date: '2026-01-15',
        anomaly_score: '0.8',
      },
    ])

    expect(issues).toEqual([])
  })

  it('accepts DE-SynPUF YYYYMMDD dates without flagging them invalid', () => {
    const issues = validateRecordRows(feed, [
      {
        claim_id: 'c1',
        provider_npi: '1234567890',
        billed_amount: '99.50',
        service_date: '20100101',
        anomaly_score: '0.8',
      },
    ])

    expect(issues).toEqual([])
  })

  it('accepts NPPES MM/DD/YYYY dates including single-digit components', () => {
    const issues = validateRecordRows(feed, [
      {
        claim_id: 'c1',
        provider_npi: '1234567890',
        billed_amount: '99.50',
        service_date: '05/23/2005',
        anomaly_score: '0.8',
      },
      {
        claim_id: 'c2',
        provider_npi: '1234567890',
        billed_amount: '99.50',
        service_date: '9/5/2008',
        anomaly_score: '0.8',
      },
    ])

    expect(issues).toEqual([])
  })

  it('still rejects calendar-invalid YYYYMMDD and MM/DD/YYYY dates', () => {
    const issues = validateRecordRows(feed, [
      {
        claim_id: 'c1',
        provider_npi: '1234567890',
        billed_amount: '99.50',
        service_date: '20251345',
        anomaly_score: '0.8',
      },
      {
        claim_id: 'c2',
        provider_npi: '1234567890',
        billed_amount: '99.50',
        service_date: '13/45/2005',
        anomaly_score: '0.8',
      },
    ])

    expect(issues.map((issue) => issue.message)).toEqual([
      'Row 1 field Date of Service must be a valid date.',
      'Row 2 field Date of Service must be a valid date.',
    ])
  })
})

describe('isValidDateValue', () => {
  it('accepts ISO YYYY-MM-DD', () => {
    expect(isValidDateValue('2024-01-15')).toBe(true)
  })

  it('accepts compact YYYYMMDD', () => {
    expect(isValidDateValue('20240115')).toBe(true)
  })

  it('accepts MM/DD/YYYY with single-digit month and day', () => {
    expect(isValidDateValue('1/5/2024')).toBe(true)
  })

  it('accepts MM/DD/YYYY with leading zeros', () => {
    expect(isValidDateValue('01/05/2024')).toBe(true)
  })

  it('rejects ambiguous year-only strings the backend would reject', () => {
    expect(isValidDateValue('2024')).toBe(false)
  })

  it('rejects locale-dependent month-name strings', () => {
    expect(isValidDateValue('Jan 1')).toBe(false)
    expect(isValidDateValue('January 1, 2024')).toBe(false)
  })

  it('rejects ISO datetime strings with timezone suffixes the backend rejects', () => {
    expect(isValidDateValue('2024-01-15T10:00:00Z')).toBe(false)
  })

  it('rejects empty and whitespace-only strings', () => {
    expect(isValidDateValue('')).toBe(false)
    expect(isValidDateValue('   ')).toBe(false)
  })

  it('rejects malformed digit groupings', () => {
    expect(isValidDateValue('2024011')).toBe(false)
    expect(isValidDateValue('13/40/2024')).toBe(false)
  })

  it('rejects non-string non-Date inputs', () => {
    expect(isValidDateValue(20240115)).toBe(false)
    expect(isValidDateValue(null)).toBe(false)
    expect(isValidDateValue(undefined)).toBe(false)
  })

  it('accepts a valid Date object', () => {
    expect(isValidDateValue(new Date('2024-01-15'))).toBe(true)
  })
})

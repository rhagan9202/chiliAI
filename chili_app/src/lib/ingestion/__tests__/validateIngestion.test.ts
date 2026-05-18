import { describe, expect, it } from 'vitest'

import type { RecordFeedConfig, ValidationConfig } from '../../../api/contracts'
import {
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
    ).toMatchObject([{ id: 'missing-feed', severity: 'error', source: 'client' }])
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
})

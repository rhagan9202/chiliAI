// @vitest-environment node
// Pure node fs data-integrity test — no DOM needed, and jsdom rewrites
// import.meta.url to an http: scheme, so keep it off the default environment.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  PUBLIC_AIR_FORCE_INSTALLATIONS,
  publicReferenceById,
  publicReferenceInstallations,
  publicReferenceMapPoints,
} from '../airForceInstallations'

// Vitest runs with cwd at the chili_app package root; the tracked fixture CSV
// lives in the repo-level docs tree one directory above.
const CSV_PATH = resolve(
  process.cwd(),
  '../docs/testing/knowledge_base_fixtures/air_force_housing/installations_reference.csv',
)

const CSV_COLUMNS = [
  'installation_id',
  'name',
  'branch',
  'command',
  'state',
  'municipality',
  'latitude',
  'longitude',
  'host_unit',
  'source_note',
] as const

type CsvRow = Record<(typeof CSV_COLUMNS)[number], string>

const CONUS_BOUNDS = { minLat: 24, maxLat: 50, minLon: -125, maxLon: -66 }

const REQUIRED_USSF_IDS = [
  'peterson_sfb',
  'schriever_sfb',
  'buckley_sfb',
  'vandenberg_sfb',
  'patrick_sfb',
  'cape_canaveral_sfs',
  'los_angeles_afb',
] as const

function readCsvRows(): CsvRow[] {
  const raw = readFileSync(CSV_PATH, 'utf8')
  const lines = raw.trim().split('\n')
  const header = lines[0].split(',')
  expect(header).toEqual([...CSV_COLUMNS])
  return lines.slice(1).map((line) => {
    const cells = line.split(',')
    expect(cells, `malformed CSV line: ${line}`).toHaveLength(CSV_COLUMNS.length)
    return Object.fromEntries(CSV_COLUMNS.map((column, index) => [column, cells[index]])) as CsvRow
  })
}

describe('airForceInstallations reference data', () => {
  const csvRows = readCsvRows()

  it('has unique installation IDs in both the CSV and the TS module', () => {
    const csvIds = csvRows.map((row) => row.installation_id)
    expect(new Set(csvIds).size).toBe(csvIds.length)

    const tsIds = PUBLIC_AIR_FORCE_INSTALLATIONS.map((installation) => installation.id)
    expect(new Set(tsIds).size).toBe(tsIds.length)
  })

  it('keeps the CSV and TS module installation sets identical', () => {
    const csvIds = [...csvRows.map((row) => row.installation_id)].sort()
    const tsIds = [...PUBLIC_AIR_FORCE_INSTALLATIONS.map((installation) => installation.id)].sort()
    expect(tsIds).toEqual(csvIds)
  })

  it('preserves the pre-existing canonical IDs', () => {
    const ids = new Set(csvRows.map((row) => row.installation_id))
    expect(ids.has('edwards_afb')).toBe(true)
    expect(ids.has('eglin_afb')).toBe(true)
  })

  it('restricts branch to USAF or USSF and requires a non-empty command', () => {
    for (const row of csvRows) {
      expect(['USAF', 'USSF'], `branch for ${row.installation_id}`).toContain(row.branch)
      expect(row.command.length, `command for ${row.installation_id}`).toBeGreaterThan(0)
    }
    for (const installation of PUBLIC_AIR_FORCE_INSTALLATIONS) {
      expect(['USAF', 'USSF'], `branch for ${installation.id}`).toContain(installation.branch)
      expect(installation.command.length, `command for ${installation.id}`).toBeGreaterThan(0)
    }
  })

  it('keeps coordinates within CONUS bounds where present', () => {
    for (const row of csvRows) {
      if (row.latitude === '' || row.longitude === '') continue
      const lat = Number(row.latitude)
      const lon = Number(row.longitude)
      expect(Number.isFinite(lat), `latitude for ${row.installation_id}`).toBe(true)
      expect(Number.isFinite(lon), `longitude for ${row.installation_id}`).toBe(true)
      expect(lat, `latitude for ${row.installation_id}`).toBeGreaterThanOrEqual(CONUS_BOUNDS.minLat)
      expect(lat, `latitude for ${row.installation_id}`).toBeLessThanOrEqual(CONUS_BOUNDS.maxLat)
      expect(lon, `longitude for ${row.installation_id}`).toBeGreaterThanOrEqual(CONUS_BOUNDS.minLon)
      expect(lon, `longitude for ${row.installation_id}`).toBeLessThanOrEqual(CONUS_BOUNDS.maxLon)
    }
    for (const installation of PUBLIC_AIR_FORCE_INSTALLATIONS) {
      expect(installation.latitude, `latitude for ${installation.id}`).toBeGreaterThanOrEqual(CONUS_BOUNDS.minLat)
      expect(installation.latitude, `latitude for ${installation.id}`).toBeLessThanOrEqual(CONUS_BOUNDS.maxLat)
      expect(installation.longitude, `longitude for ${installation.id}`).toBeGreaterThanOrEqual(CONUS_BOUNDS.minLon)
      expect(installation.longitude, `longitude for ${installation.id}`).toBeLessThanOrEqual(CONUS_BOUNDS.maxLon)
    }
  })

  it('includes the required minimum USSF installation set', () => {
    const csvIds = new Set(csvRows.map((row) => row.installation_id))
    const tsIds = new Set(PUBLIC_AIR_FORCE_INSTALLATIONS.map((installation) => installation.id))
    for (const id of REQUIRED_USSF_IDS) {
      expect(csvIds.has(id), `CSV missing ${id}`).toBe(true)
      expect(tsIds.has(id), `TS module missing ${id}`).toBe(true)
    }
  })

  it('keeps CSV row fields aligned with the TS module records', () => {
    const byId = publicReferenceById()
    for (const row of csvRows) {
      const installation = byId.get(row.installation_id)
      expect(installation, `TS module missing ${row.installation_id}`).toBeDefined()
      if (!installation) continue
      expect(installation.name).toBe(row.name)
      expect(installation.branch).toBe(row.branch)
      expect(installation.command).toBe(row.command)
      expect(installation.state).toBe(row.state)
      expect(installation.municipality).toBe(row.municipality)
      if (row.latitude !== '' && row.longitude !== '') {
        expect(installation.latitude).toBeCloseTo(Number(row.latitude), 4)
        expect(installation.longitude).toBeCloseTo(Number(row.longitude), 4)
      }
    }
  })

  it('exposes the full set through the preserved public API', () => {
    const installations = publicReferenceInstallations()
    expect(installations).toHaveLength(PUBLIC_AIR_FORCE_INSTALLATIONS.length)
    for (const item of installations) {
      expect(item.majcom).toBeTruthy()
      expect(item.branch).toBeTruthy()
    }

    const mapPoints = publicReferenceMapPoints()
    expect(mapPoints).toHaveLength(PUBLIC_AIR_FORCE_INSTALLATIONS.length)
    for (const point of mapPoints) {
      expect(Number.isFinite(point.latitude)).toBe(true)
      expect(Number.isFinite(point.longitude)).toBe(true)
    }

    expect(publicReferenceById().size).toBe(PUBLIC_AIR_FORCE_INSTALLATIONS.length)
  })
})

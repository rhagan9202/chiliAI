import { geoAlbersUsa, geoGraticule, geoPath } from 'd3-geo'
import { feature } from 'topojson-client'
import usAtlasStates from 'us-atlas/states-albers-10m.json'

import type { HousingInstallationResponse } from '../../api/contracts'

type InstallationStatus = HousingInstallationResponse['status']

// us-atlas `states-albers-10m.json` ships pre-projected into a 975x610 frame by
// geoAlbersUsa().scale(1300).translate([487.5, 305]). Rendering the shapes with an
// unprojected geoPath while projecting marker lat/lon through the same projection
// keeps geography and markers in exact registration. The asset is ~84KB raw
// (~25KB gzipped), small enough for a static import.
export const MAP_VIEWBOX_WIDTH = 975
export const MAP_VIEWBOX_HEIGHT = 610

const markerProjection = geoAlbersUsa()
  .scale(1300)
  .translate([MAP_VIEWBOX_WIDTH / 2, MAP_VIEWBOX_HEIGHT / 2])

// geoAlbersUsa composites Alaska and Hawaii as bottom-left insets. This dashboard
// plots CONUS installations only, so the insets would always render empty; omit
// them and reclaim the corner for the legend. Re-add these ids (02, 15) alongside
// inset frames if OCONUS coverage ever lands.
const NON_CONUS_STATE_IDS: ReadonlySet<string> = new Set(['02', '15'])

export type StateShape = {
  id: string
  name: string
  d: string
}

function buildStateShapes(): StateShape[] {
  const statesCollection = feature(usAtlasStates, usAtlasStates.objects.states)
  const renderPath = geoPath()
  const shapes: StateShape[] = []
  for (const stateFeature of statesCollection.features) {
    const id = String(stateFeature.id ?? '')
    if (NON_CONUS_STATE_IDS.has(id)) {
      continue
    }
    const d = renderPath(stateFeature)
    if (d) {
      shapes.push({ id, name: stateFeature.properties.name, d })
    }
  }
  return shapes
}

export const CONUS_STATE_SHAPES: readonly StateShape[] = buildStateShapes()

// Subtle lat/lon graticule clipped to the CONUS window; projected through the same
// Albers USA projection as the markers so it registers with the state shapes.
export const CONUS_GRATICULE_PATH: string =
  geoPath(markerProjection)(
    geoGraticule()
      .step([8, 8])
      .extent([
        [-126, 24],
        [-66, 50.5],
      ])(),
  ) ?? ''

export type ProjectedPoint = {
  xPct: number
  yPct: number
}

export type ProjectedPointVb = {
  x: number
  y: number
}

// geoAlbersUsa also projects Alaska/Hawaii coordinates — into the bottom-left
// inset windows whose state shapes we deliberately omit. Reject anything outside
// this CONUS window so such points take the visible "location pending" path
// instead of floating over blank canvas (red-cell finding A3).
const CONUS_BOUNDS = {
  minLatitude: 23.5,
  maxLatitude: 50.5,
  minLongitude: -125.5,
  maxLongitude: -66.5,
}

/**
 * Project WGS84 coordinates into the 975x610 viewBox frame.
 * Returns null when the point falls outside the Albers USA composite OR outside
 * the CONUS window (e.g. AK/HI inset region) — callers must surface such points
 * via the location-pending path, never drop them.
 */
export function projectMapPointVb(latitude: number, longitude: number): ProjectedPointVb | null {
  if (
    latitude < CONUS_BOUNDS.minLatitude ||
    latitude > CONUS_BOUNDS.maxLatitude ||
    longitude < CONUS_BOUNDS.minLongitude ||
    longitude > CONUS_BOUNDS.maxLongitude
  ) {
    return null
  }
  const projected = markerProjection([longitude, latitude])
  if (!projected) {
    return null
  }
  return { x: projected[0], y: projected[1] }
}

/** Same projection expressed as percentage offsets within the map frame. */
export function projectMapPoint(latitude: number, longitude: number): ProjectedPoint | null {
  const projected = projectMapPointVb(latitude, longitude)
  if (!projected) {
    return null
  }
  return {
    xPct: (projected.x / MAP_VIEWBOX_WIDTH) * 100,
    yPct: (projected.y / MAP_VIEWBOX_HEIGHT) * 100,
  }
}

// Minimum center-to-center marker separation in viewBox units. 44vb renders to
// ~17.8px at the ~394px-wide frame measured at a 1280px demo viewport, which
// clears the 24px hit target's worst-case diagonal cover distance
// (12*sqrt(2) ~= 17px) so every marker stays mouse-reachable (red-cell A2).
export const MIN_MARKER_SEPARATION_VB = 44

export type DeclutterInput = {
  id: string
  x: number
  y: number
}

export type DeclutteredPoint = {
  id: string
  x: number
  y: number
  anchorX: number
  anchorY: number
  displaced: boolean
}

const RELAXATION_MAX_ITERATIONS = 200
const DISPLACED_EPSILON_VB = 0.5

/**
 * Deterministic pairwise-repulsion declutter (red-cell finding A2): any two
 * markers closer than `minSeparation` are pushed apart along their axis until
 * every pair clears it. Relaxation (rather than ring/spiderfy placement) keeps
 * displacements minimal and local, and handles chain clusters (e.g. the
 * Texas–Oklahoma corridor) without mega-ring artifacts. Input is sorted by id
 * so the result is stable regardless of caller ordering; exact ties break
 * vertically by sort order. Each marker keeps its true location as an anchor so
 * the component can draw a leader leg back to it.
 */
export function declutterMarkers(
  points: readonly DeclutterInput[],
  minSeparation: number = MIN_MARKER_SEPARATION_VB,
): DeclutteredPoint[] {
  const working: DeclutteredPoint[] = [...points]
    .sort((a, b) => a.id.localeCompare(b.id))
    .map((point) => ({
      id: point.id,
      x: point.x,
      y: point.y,
      anchorX: point.x,
      anchorY: point.y,
      displaced: false,
    }))
  for (let iteration = 0; iteration < RELAXATION_MAX_ITERATIONS; iteration += 1) {
    let moved = false
    for (let a = 0; a < working.length; a += 1) {
      for (let b = a + 1; b < working.length; b += 1) {
        const first = working[a]
        const second = working[b]
        const dx = second.x - first.x
        const dy = second.y - first.y
        const distance = Math.hypot(dx, dy)
        if (distance >= minSeparation) {
          continue
        }
        moved = true
        // Push slightly past the threshold so convergence is strict, not asymptotic.
        const push = (minSeparation - distance) / 2 + 0.05
        if (distance === 0) {
          first.y -= push
          second.y += push
        } else {
          const ux = dx / distance
          const uy = dy / distance
          first.x -= ux * push
          first.y -= uy * push
          second.x += ux * push
          second.y += uy * push
        }
      }
    }
    if (!moved) {
      break
    }
  }
  for (const point of working) {
    point.displaced =
      Math.hypot(point.x - point.anchorX, point.y - point.anchorY) > DISPLACED_EPSILON_VB
  }
  return working
}

export type InstallationBranch = 'USAF' | 'USSF'

export function normalizeBranch(branch: string | null | undefined): InstallationBranch | null {
  return branch === 'USAF' || branch === 'USSF' ? branch : null
}

const WORK_ORDER_BAND_SIZE = 35
const MAX_WORK_ORDER_BAND = 3

export function workOrderBand(openWorkOrders: number): number {
  return Math.min(Math.max(Math.floor(openWorkOrders / WORK_ORDER_BAND_SIZE), 0), MAX_WORK_ORDER_BAND)
}

/** Marker diameter encodes the open work-order band only; color stays status-only. */
export function markerDiameterPx(openWorkOrders: number): number {
  return 12 + workOrderBand(openWorkOrders) * 4
}

export const STATUS_WEIGHT: Record<InstallationStatus, number> = {
  ok: 0,
  unknown: 1,
  watch: 2,
  critical: 3,
}

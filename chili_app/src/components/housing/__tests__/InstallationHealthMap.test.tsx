import { fireEvent, render, screen, within } from '@testing-library/react'
import { geoAlbersUsa } from 'd3-geo'
import { describe, expect, it, vi } from 'vitest'

import type {
  HousingInstallationMapPointResponse,
  HousingInstallationResponse,
} from '../../../api/contracts'
import { InstallationHealthMap } from '../InstallationHealthMap'
import {
  CONUS_GRATICULE_PATH,
  CONUS_STATE_SHAPES,
  declutterMarkers,
  MAP_VIEWBOX_HEIGHT,
  MAP_VIEWBOX_WIDTH,
  markerDiameterPx,
  MIN_MARKER_SEPARATION_VB,
  normalizeBranch,
  projectMapPoint,
  projectMapPointVb,
  workOrderBand,
} from '../installationMapGeometry'

const installations: HousingInstallationResponse[] = [
  {
    installation_id: 'eglin_afb',
    name: 'Eglin AFB',
    branch: 'USAF',
    majcom: 'AFMC',
    state: 'FL',
    status: 'critical',
    open_work_orders: 120,
    occupancy_rate: 0.9,
  },
  {
    installation_id: 'peterson_sfb',
    name: 'Peterson SFB',
    branch: 'USSF',
    majcom: 'SpOC',
    state: 'CO',
    status: 'watch',
    open_work_orders: 40,
    occupancy_rate: 0.88,
  },
  {
    installation_id: 'edwards_afb',
    name: 'Edwards AFB',
    branch: 'USAF',
    majcom: 'AFMC',
    state: 'CA',
    status: 'ok',
    open_work_orders: 10,
    occupancy_rate: 0.93,
  },
]

const mapPoints: HousingInstallationMapPointResponse[] = [
  {
    installation_id: 'eglin_afb',
    name: 'Eglin AFB',
    branch: 'USAF',
    latitude: 30.4832,
    longitude: -86.5254,
    status: 'critical',
  },
  {
    installation_id: 'peterson_sfb',
    name: 'Peterson SFB',
    branch: 'USSF',
    latitude: 38.8158,
    longitude: -104.7003,
    status: 'watch',
  },
  {
    installation_id: 'edwards_afb',
    name: 'Edwards AFB',
    branch: 'USAF',
    latitude: 34.9054,
    longitude: -117.8837,
    status: 'ok',
  },
]

function renderMap(overrides: Partial<Parameters<typeof InstallationHealthMap>[0]> = {}) {
  const onSelectInstallation = vi.fn()
  const view = render(
    <InstallationHealthMap
      installations={installations}
      mapPoints={mapPoints}
      onSelectInstallation={onSelectInstallation}
      selectedInstallationId="eglin_afb"
      {...overrides}
    />,
  )
  return { onSelectInstallation, view }
}

describe('installationMapGeometry', () => {
  it('projects markers with the standard Albers USA pairing for the 975x610 frame', () => {
    const reference = geoAlbersUsa()
      .scale(1300)
      .translate([MAP_VIEWBOX_WIDTH / 2, MAP_VIEWBOX_HEIGHT / 2])

    for (const point of mapPoints) {
      const expected = reference([point.longitude, point.latitude])
      const actual = projectMapPoint(point.latitude, point.longitude)
      expect(expected).not.toBeNull()
      expect(actual).not.toBeNull()
      expect(actual?.xPct).toBeCloseTo(((expected as [number, number])[0] / MAP_VIEWBOX_WIDTH) * 100, 6)
      expect(actual?.yPct).toBeCloseTo(((expected as [number, number])[1] / MAP_VIEWBOX_HEIGHT) * 100, 6)
    }
  })

  it('places CONUS installations in geographically sensible positions', () => {
    const eglin = projectMapPoint(30.4832, -86.5254)
    const peterson = projectMapPoint(38.8158, -104.7003)
    const edwards = projectMapPoint(34.9054, -117.8837)

    expect(eglin).not.toBeNull()
    expect(peterson).not.toBeNull()
    expect(edwards).not.toBeNull()
    // West-to-east ordering: Edwards (CA) < Peterson (CO) < Eglin (FL panhandle).
    expect(edwards!.xPct).toBeLessThan(peterson!.xPct)
    expect(peterson!.xPct).toBeLessThan(eglin!.xPct)
    // Eglin sits well south of Peterson.
    expect(eglin!.yPct).toBeGreaterThan(peterson!.yPct)
    for (const projected of [eglin!, peterson!, edwards!]) {
      expect(projected.xPct).toBeGreaterThan(0)
      expect(projected.xPct).toBeLessThan(100)
      expect(projected.yPct).toBeGreaterThan(0)
      expect(projected.yPct).toBeLessThan(100)
    }
  })

  it('returns null for coordinates outside the Albers USA composite', () => {
    expect(projectMapPoint(51.5074, -0.1278)).toBeNull()
  })

  it('rejects AK/HI coordinates even though the composite would project them into insets', () => {
    // Hickam AFB (Honolulu) and JBER (Anchorage) would land in the removed
    // inset windows — they must route to location pending, not float on canvas.
    expect(projectMapPointVb(21.3187, -157.9224)).toBeNull()
    expect(projectMapPoint(61.2506, -149.8068)).toBeNull()
  })

  it('spreads co-located markers apart deterministically while keeping true anchors', () => {
    const input = [
      { id: 'peterson_sfb', x: 346, y: 295 },
      { id: 'schriever_sfb', x: 349, y: 296 },
      { id: 'usafa', x: 344, y: 288 },
      { id: 'edwards_afb', x: 100, y: 340 },
    ]
    const first = declutterMarkers(input)
    const second = declutterMarkers(input)
    expect(second).toEqual(first)

    const byId = new Map(first.map((placed) => [placed.id, placed]))
    const edwards = byId.get('edwards_afb')
    expect(edwards).toMatchObject({ x: 100, y: 340, displaced: false })

    const cluster = ['peterson_sfb', 'schriever_sfb', 'usafa'].map((id) => byId.get(id)!)
    for (const member of cluster) {
      expect(member.displaced).toBe(true)
      // True location preserved as the leader-leg anchor.
      const original = input.find((point) => point.id === member.id)!
      expect(member.anchorX).toBe(original.x)
      expect(member.anchorY).toBe(original.y)
    }
    for (let a = 0; a < first.length; a += 1) {
      for (let b = a + 1; b < first.length; b += 1) {
        const distance = Math.hypot(first[a].x - first[b].x, first[a].y - first[b].y)
        expect(distance).toBeGreaterThanOrEqual(MIN_MARKER_SEPARATION_VB - 1e-6)
      }
    }
  })

  it('builds real CONUS geography: 48 states plus DC, no Alaska or Hawaii', () => {
    expect(CONUS_STATE_SHAPES).toHaveLength(49)
    const names = CONUS_STATE_SHAPES.map((state) => state.name)
    expect(names).toContain('Florida')
    expect(names).toContain('Colorado')
    expect(names).not.toContain('Alaska')
    expect(names).not.toContain('Hawaii')
    for (const state of CONUS_STATE_SHAPES) {
      expect(state.d.length).toBeGreaterThan(10)
    }
    expect(CONUS_GRATICULE_PATH.length).toBeGreaterThan(100)
  })

  it('bands marker size by open work orders only', () => {
    expect(workOrderBand(0)).toBe(0)
    expect(workOrderBand(34)).toBe(0)
    expect(workOrderBand(35)).toBe(1)
    expect(workOrderBand(500)).toBe(3)
    expect(markerDiameterPx(0)).toBe(12)
    expect(markerDiameterPx(120)).toBe(24)
  })

  it('normalizes branch values null-safely', () => {
    expect(normalizeBranch('USAF')).toBe('USAF')
    expect(normalizeBranch('USSF')).toBe('USSF')
    expect(normalizeBranch(null)).toBeNull()
    expect(normalizeBranch(undefined)).toBeNull()
    expect(normalizeBranch('ARMY')).toBeNull()
  })
})

describe('InstallationHealthMap', () => {
  it('renders real state geography inside the SVG', () => {
    const { view } = renderMap()
    const svg = screen.getByLabelText('Installation health map')
    const statePaths = view.container.querySelectorAll('path[data-state]')
    expect(svg).toBeInTheDocument()
    expect(statePaths).toHaveLength(49)
  })

  it('positions markers at projected coordinates with status and branch encodings', () => {
    renderMap()

    const eglin = screen.getByRole('button', {
      name: 'Select Eglin AFB on map, critical status, 120 open work orders, USAF',
    })
    const projected = projectMapPoint(30.4832, -86.5254)
    expect(projected).not.toBeNull()
    expect(eglin.style.left).toBe(`${projected!.xPct}%`)
    expect(eglin.style.top).toBe(`${projected!.yPct}%`)
    expect(eglin.dataset.status).toBe('critical')
    expect(eglin.dataset.branch).toBe('USAF')

    const peterson = screen.getByRole('button', {
      name: 'Select Peterson SFB on map, watch status, 40 open work orders, USSF',
    })
    expect(peterson.dataset.branch).toBe('USSF')
    expect(peterson.dataset.status).toBe('watch')
  })

  it('keeps DOM/tab order geographic west-to-east while severity stacks via z-index', () => {
    renderMap()

    const markers = [...document.querySelectorAll('button[data-status]')]
    const names = markers.map((marker) => marker.getAttribute('aria-label'))
    // Edwards (CA) < Peterson (CO) < Eglin (FL) in tab order regardless of severity.
    expect(names[0]).toContain('Edwards AFB')
    expect(names[1]).toContain('Peterson SFB')
    expect(names[2]).toContain('Eglin AFB')
    // Critical paints on top through z-index, not DOM position.
    expect((markers[2] as HTMLElement).style.getPropertyValue('--marker-z')).toBe('4')
    expect((markers[0] as HTMLElement).style.getPropertyValue('--marker-z')).toBe('1')
  })

  it('declutters co-located markers with leader legs back to true locations', () => {
    const { view } = renderMap({
      mapPoints: [
        ...mapPoints,
        {
          installation_id: 'schriever_sfb',
          name: 'Schriever SFB',
          branch: 'USSF',
          latitude: 38.8031,
          longitude: -104.5283,
          status: 'unknown',
        },
      ],
      installations: [
        ...installations,
        {
          installation_id: 'schriever_sfb',
          name: 'Schriever SFB',
          branch: 'USSF',
          majcom: 'SpOC',
          state: 'CO',
          status: 'unknown',
          open_work_orders: 0,
          occupancy_rate: null,
        },
      ],
    })

    const peterson = screen.getByRole('button', { name: /select peterson sfb on map/i })
    const schriever = screen.getByRole('button', { name: /select schriever sfb on map/i })
    const toVb = (marker: HTMLElement) => ({
      x: (parseFloat(marker.style.left) / 100) * MAP_VIEWBOX_WIDTH,
      y: (parseFloat(marker.style.top) / 100) * MAP_VIEWBOX_HEIGHT,
    })
    const petersonVb = toVb(peterson)
    const schrieverVb = toVb(schriever)
    expect(
      Math.hypot(petersonVb.x - schrieverVb.x, petersonVb.y - schrieverVb.y),
    ).toBeGreaterThanOrEqual(MIN_MARKER_SEPARATION_VB - 1e-6)

    const legs = view.container.querySelectorAll('[data-leg]')
    expect(legs).toHaveLength(2)
    expect(view.container.querySelector('[data-leg="peterson_sfb"] line')).not.toBeNull()
    expect(view.container.querySelector('[data-leg="peterson_sfb"] circle')).not.toBeNull()
  })

  it('handles selection via click and reflects aria-pressed', () => {
    const { onSelectInstallation } = renderMap()

    const eglin = screen.getByRole('button', { name: /select eglin afb on map/i })
    expect(eglin).toHaveAttribute('aria-pressed', 'true')

    const edwards = screen.getByRole('button', { name: /select edwards afb on map/i })
    expect(edwards).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(edwards)
    expect(onSelectInstallation).toHaveBeenCalledWith('edwards_afb')
  })

  it('shows a tooltip on hover and hides it on leave', () => {
    renderMap()

    expect(screen.queryByTestId('map-tooltip')).not.toBeInTheDocument()
    const peterson = screen.getByRole('button', { name: /select peterson sfb on map/i })
    fireEvent.mouseEnter(peterson)

    const tooltip = screen.getByTestId('map-tooltip')
    expect(within(tooltip).getByText('Peterson SFB')).toBeInTheDocument()
    expect(within(tooltip).getByText('Watch · 40 open work orders')).toBeInTheDocument()
    expect(within(tooltip).getByText('USSF')).toBeInTheDocument()

    fireEvent.mouseLeave(peterson)
    expect(screen.queryByTestId('map-tooltip')).not.toBeInTheDocument()
  })

  it('shows the tooltip on keyboard focus for accessibility', () => {
    renderMap()

    const eglin = screen.getByRole('button', { name: /select eglin afb on map/i })
    fireEvent.focus(eglin)
    expect(screen.getByTestId('map-tooltip')).toBeInTheDocument()
    fireEvent.blur(eglin)
    expect(screen.queryByTestId('map-tooltip')).not.toBeInTheDocument()
  })

  it('lists installations without map points as location pending instead of dropping them', () => {
    const { onSelectInstallation } = renderMap({
      installations: [
        ...installations,
        {
          installation_id: 'holloman_afb',
          name: 'Holloman AFB',
          branch: 'USAF',
          majcom: 'ACC',
          state: 'NM',
          status: 'unknown',
          open_work_orders: 0,
          occupancy_rate: null,
        },
      ],
    })

    const pending = screen.getByRole('group', { name: 'Installations with location pending' })
    expect(within(pending).getByText('Location pending (1)')).toBeInTheDocument()
    const pendingButton = within(pending).getByRole('button', { name: /holloman afb/i })
    expect(within(pendingButton).getByText('no coordinates')).toBeInTheDocument()

    fireEvent.click(pendingButton)
    expect(onSelectInstallation).toHaveBeenCalledWith('holloman_afb')
  })

  it('surfaces map points that fail projection as location pending, not silently dropped', () => {
    renderMap({
      mapPoints: [
        ...mapPoints,
        {
          installation_id: 'offshore_site',
          name: 'Offshore Site',
          branch: null,
          latitude: 51.5074,
          longitude: -0.1278,
          status: 'unknown',
        },
      ],
    })

    expect(screen.queryByRole('button', { name: /select offshore site on map/i })).not.toBeInTheDocument()
    const pending = screen.getByRole('group', { name: 'Installations with location pending' })
    const pendingButton = within(pending).getByRole('button', { name: /offshore site/i })
    expect(within(pendingButton).getByText('outside map frame')).toBeInTheDocument()
  })

  it('omits the pending strip when every installation is plotted', () => {
    renderMap()
    expect(
      screen.queryByRole('group', { name: 'Installations with location pending' }),
    ).not.toBeInTheDocument()
  })

  it('renders reference mode with unknown styling and pending-status labels', () => {
    renderMap({
      referenceMode: true,
      selectedInstallationId: null,
      installations: installations.map((installation) => ({
        ...installation,
        status: 'unknown' as const,
        open_work_orders: 0,
        occupancy_rate: null,
      })),
      mapPoints: mapPoints.map((point) => ({ ...point, status: 'unknown' as const })),
    })

    const eglin = screen.getByRole('button', {
      name: 'Select Eglin AFB on map, public reference location, live housing status pending, USAF',
    })
    expect(eglin.dataset.status).toBe('unknown')

    fireEvent.mouseEnter(eglin)
    const tooltip = screen.getByTestId('map-tooltip')
    expect(within(tooltip).getByText('Live housing status pending')).toBeInTheDocument()
  })

  it('treats a missing branch as unspecified without crashing', () => {
    renderMap({
      mapPoints: mapPoints.map((point) => ({ ...point, branch: null })),
      installations: installations.map((installation) => ({ ...installation, branch: null })),
    })

    const eglin = screen.getByRole('button', { name: /select eglin afb on map/i })
    expect(eglin.dataset.branch).toBe('unspecified')
  })
})

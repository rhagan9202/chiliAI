import { useMemo, useState } from 'react'
import type { CSSProperties } from 'react'

import type {
  HousingInstallationMapPointResponse,
  HousingInstallationResponse,
} from '../../api/contracts'
import {
  CONUS_GRATICULE_PATH,
  CONUS_STATE_SHAPES,
  declutterMarkers,
  MAP_VIEWBOX_HEIGHT,
  MAP_VIEWBOX_WIDTH,
  markerDiameterPx,
  normalizeBranch,
  projectMapPointVb,
  STATUS_WEIGHT,
  type InstallationBranch,
} from './installationMapGeometry'
import styles from './InstallationHealthMap.module.css'

type InstallationStatus = HousingInstallationResponse['status']

type InstallationHealthMapProps = {
  installations: HousingInstallationResponse[]
  mapPoints: HousingInstallationMapPointResponse[]
  referenceMode?: boolean
  selectedInstallationId: string | null
  onSelectInstallation: (installationId: string) => void
}

const STATUS_COLOR: Record<InstallationStatus, string> = {
  ok: 'var(--c-green)',
  watch: 'var(--c-amber)',
  critical: 'var(--c-red)',
  unknown: 'var(--c-dim)',
}

const STATUS_LABEL: Record<InstallationStatus, string> = {
  ok: 'OK',
  watch: 'Watch',
  critical: 'Critical',
  unknown: 'Unknown',
}

type PlottedMarker = {
  point: HousingInstallationMapPointResponse
  status: InstallationStatus
  branch: InstallationBranch | null
  openWorkOrders: number
  xPct: number
  yPct: number
  anchorXPct: number
  anchorYPct: number
  displaced: boolean
}

type PendingLocation = {
  installationId: string
  name: string
  reason: 'no coordinates' | 'outside map frame'
}

function markerAriaLabel(marker: PlottedMarker, referenceMode: boolean): string {
  const branchSuffix = marker.branch ? `, ${marker.branch}` : ''
  if (referenceMode) {
    return `Select ${marker.point.name} on map, public reference location, live housing status pending${branchSuffix}`
  }
  return `Select ${marker.point.name} on map, ${marker.status} status, ${marker.openWorkOrders} open work orders${branchSuffix}`
}

function tooltipShiftX(xPct: number): string {
  // Horizontal clamp so tooltips near the east/west frame edges are not clipped
  // by the root's overflow:hidden (red-cell finding A4).
  if (xPct <= 16) {
    return '-6%'
  }
  if (xPct >= 84) {
    return '-94%'
  }
  return '-50%'
}

export function InstallationHealthMap({
  installations,
  mapPoints,
  referenceMode = false,
  selectedInstallationId,
  onSelectInstallation,
}: InstallationHealthMapProps) {
  const [hoveredInstallationId, setHoveredInstallationId] = useState<string | null>(null)

  const { plottedMarkers, pendingLocations } = useMemo(() => {
    const installationById = new Map(
      installations.map((installation) => [installation.installation_id, installation]),
    )
    const projectable: {
      point: HousingInstallationMapPointResponse
      status: InstallationStatus
      branch: InstallationBranch | null
      openWorkOrders: number
      x: number
      y: number
    }[] = []
    const pending: PendingLocation[] = []
    const plottedIds = new Set<string>()

    for (const point of mapPoints) {
      const installation = installationById.get(point.installation_id)
      const projected = projectMapPointVb(point.latitude, point.longitude)
      if (!projected) {
        // Outside the Albers USA composite or the CONUS window — surfaced below, never dropped.
        pending.push({
          installationId: point.installation_id,
          name: point.name,
          reason: 'outside map frame',
        })
        plottedIds.add(point.installation_id)
        continue
      }
      projectable.push({
        point,
        status: installation?.status ?? point.status,
        branch: normalizeBranch(point.branch ?? installation?.branch),
        openWorkOrders: installation?.open_work_orders ?? 0,
        x: projected.x,
        y: projected.y,
      })
      plottedIds.add(point.installation_id)
    }

    for (const installation of installations) {
      if (!plottedIds.has(installation.installation_id)) {
        pending.push({
          installationId: installation.installation_id,
          name: installation.name,
          reason: 'no coordinates',
        })
      }
    }

    // Spread co-located markers so every installation stays mouse-reachable;
    // a leader leg is drawn back to each displaced marker's true location.
    const decluttered = new Map(
      declutterMarkers(
        projectable.map((entry) => ({ id: entry.point.installation_id, x: entry.x, y: entry.y })),
      ).map((placed) => [placed.id, placed]),
    )
    const plotted: PlottedMarker[] = projectable.map((entry) => {
      const placed = decluttered.get(entry.point.installation_id)
      const x = placed?.x ?? entry.x
      const y = placed?.y ?? entry.y
      return {
        point: entry.point,
        status: entry.status,
        branch: entry.branch,
        openWorkOrders: entry.openWorkOrders,
        xPct: (x / MAP_VIEWBOX_WIDTH) * 100,
        yPct: (y / MAP_VIEWBOX_HEIGHT) * 100,
        anchorXPct: ((placed?.anchorX ?? entry.x) / MAP_VIEWBOX_WIDTH) * 100,
        anchorYPct: ((placed?.anchorY ?? entry.y) / MAP_VIEWBOX_HEIGHT) * 100,
        displaced: placed?.displaced ?? false,
      }
    })

    // Deliberate keyboard order (red-cell finding A6): DOM/tab order is a stable
    // geographic west-to-east sweep; severity determines STACKING via z-index
    // (see --marker-z below), not DOM position, so critical markers still paint
    // on top without scrambling keyboard traversal.
    plotted.sort((a, b) => a.xPct - b.xPct || a.yPct - b.yPct || a.point.installation_id.localeCompare(b.point.installation_id))

    return { plottedMarkers: plotted, pendingLocations: pending }
  }, [installations, mapPoints])

  const hoveredMarker =
    plottedMarkers.find((marker) => marker.point.installation_id === hoveredInstallationId) ?? null

  return (
    <div className={styles.root}>
      <div className={styles.frame}>
        <svg
          aria-label="Installation health map"
          className={styles.map}
          role="img"
          viewBox={`0 0 ${MAP_VIEWBOX_WIDTH} ${MAP_VIEWBOX_HEIGHT}`}
        >
          <path className={styles.graticule} d={CONUS_GRATICULE_PATH} />
          {CONUS_STATE_SHAPES.map((state) => (
            <path className={styles.state} d={state.d} data-state={state.id} key={state.id}>
              <title>{state.name}</title>
            </path>
          ))}
          {plottedMarkers
            .filter((marker) => marker.displaced)
            .map((marker) => (
              <g data-leg={marker.point.installation_id} key={`leg-${marker.point.installation_id}`}>
                <line
                  className={styles.legLine}
                  x1={(marker.anchorXPct / 100) * MAP_VIEWBOX_WIDTH}
                  x2={(marker.xPct / 100) * MAP_VIEWBOX_WIDTH}
                  y1={(marker.anchorYPct / 100) * MAP_VIEWBOX_HEIGHT}
                  y2={(marker.yPct / 100) * MAP_VIEWBOX_HEIGHT}
                />
                <circle
                  className={styles.legAnchor}
                  cx={(marker.anchorXPct / 100) * MAP_VIEWBOX_WIDTH}
                  cy={(marker.anchorYPct / 100) * MAP_VIEWBOX_HEIGHT}
                  r={2}
                />
              </g>
            ))}
        </svg>

        <div className={styles.markers}>
          {plottedMarkers.map((marker) => {
            const selected = marker.point.installation_id === selectedInstallationId
            const innerClasses = [styles.markerInner]
            if (marker.branch === 'USSF') {
              innerClasses.push(styles.markerInnerUssf)
            }
            return (
              <button
                aria-label={markerAriaLabel(marker, referenceMode)}
                aria-pressed={selected}
                className={selected ? `${styles.marker} ${styles.markerSelected}` : styles.marker}
                data-branch={marker.branch ?? 'unspecified'}
                data-status={marker.status}
                key={marker.point.installation_id}
                onBlur={() => setHoveredInstallationId(null)}
                onClick={() => onSelectInstallation(marker.point.installation_id)}
                onFocus={() => setHoveredInstallationId(marker.point.installation_id)}
                onMouseEnter={() => setHoveredInstallationId(marker.point.installation_id)}
                onMouseLeave={() => setHoveredInstallationId(null)}
                style={{
                  left: `${marker.xPct}%`,
                  top: `${marker.yPct}%`,
                  '--marker-color': STATUS_COLOR[marker.status],
                  '--marker-size': `${markerDiameterPx(marker.openWorkOrders)}px`,
                  '--marker-z': STATUS_WEIGHT[marker.status] + 1,
                } as CSSProperties}
                type="button"
              >
                <span className={innerClasses.join(' ')} />
              </button>
            )
          })}
        </div>

        {hoveredMarker ? (
          <div
            className={
              hoveredMarker.yPct < 18 ? `${styles.tooltip} ${styles.tooltipBelow}` : styles.tooltip
            }
            data-testid="map-tooltip"
            role="status"
            style={{
              left: `${hoveredMarker.xPct}%`,
              top: `${hoveredMarker.yPct}%`,
              '--tt-shift-x': tooltipShiftX(hoveredMarker.xPct),
            } as CSSProperties}
          >
            <strong className={styles.tooltipTitle}>{hoveredMarker.point.name}</strong>
            <span className={styles.tooltipLine}>
              {referenceMode
                ? 'Live housing status pending'
                : `${STATUS_LABEL[hoveredMarker.status]} · ${hoveredMarker.openWorkOrders} open work orders`}
            </span>
            {hoveredMarker.branch ? (
              <span className={styles.tooltipBranch}>{hoveredMarker.branch}</span>
            ) : null}
          </div>
        ) : null}
      </div>

      <div aria-hidden="true" className={styles.legend}>
        <div className={styles.legendGroup}>
          {(Object.keys(STATUS_COLOR) as InstallationStatus[]).map((status) => (
            <span className={styles.legendItem} key={status}>
              <span
                className={styles.legendDot}
                style={{ '--legend-color': STATUS_COLOR[status] } as CSSProperties}
              />
              {status}
            </span>
          ))}
        </div>
        <div className={styles.legendGroup}>
          <span className={styles.legendItem}>
            <span className={styles.legendShape} />
            USAF
          </span>
          <span className={styles.legendItem}>
            <span className={`${styles.legendShape} ${styles.legendShapeUssf}`} />
            USSF
          </span>
        </div>
        <div className={styles.legendGroup}>
          <span className={styles.legendItem}>
            <span className={styles.legendSizeSmall} />
            <span className={styles.legendSizeLarge} />
            size = open WOs
          </span>
        </div>
      </div>

      {pendingLocations.length > 0 ? (
        <div aria-label="Installations with location pending" className={styles.pending} role="group">
          <span className={styles.pendingLabel}>Location pending ({pendingLocations.length})</span>
          <ul className={styles.pendingList}>
            {pendingLocations.map((location) => (
              <li key={location.installationId}>
                <button
                  className={styles.pendingItem}
                  onClick={() => onSelectInstallation(location.installationId)}
                  type="button"
                >
                  {location.name}
                  <span className={styles.pendingReason}>{location.reason}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

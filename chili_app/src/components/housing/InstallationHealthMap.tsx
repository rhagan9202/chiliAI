import type { CSSProperties } from 'react'

import type {
  HousingInstallationMapPointResponse,
  HousingInstallationResponse,
} from '../../api/contracts'
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
  ok: '#00e676',
  watch: '#f59e0b',
  critical: '#ff4040',
  unknown: '#8899bb',
}

const STATUS_WEIGHT: Record<InstallationStatus, number> = {
  ok: 0,
  unknown: 1,
  watch: 2,
  critical: 3,
}

const MAP_BOUNDS = {
  minLatitude: 24,
  maxLatitude: 50,
  minLongitude: -125,
  maxLongitude: -66,
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}

function pointPosition(latitude: number, longitude: number) {
  const x =
    ((longitude - MAP_BOUNDS.minLongitude) /
      (MAP_BOUNDS.maxLongitude - MAP_BOUNDS.minLongitude)) *
    100
  const y =
    ((MAP_BOUNDS.maxLatitude - latitude) /
      (MAP_BOUNDS.maxLatitude - MAP_BOUNDS.minLatitude)) *
    100

  return {
    left: `${clamp(x, 3, 97)}%`,
    top: `${clamp(y, 5, 95)}%`,
  }
}

function markerSize(installation: HousingInstallationResponse | undefined, status: InstallationStatus) {
  const workOrders = installation?.open_work_orders ?? 0
  const workOrderBand = Math.min(Math.floor(workOrders / 35), 3)
  return `${14 + STATUS_WEIGHT[status] * 3 + workOrderBand * 2}px`
}

export function InstallationHealthMap({
  installations,
  mapPoints,
  referenceMode = false,
  selectedInstallationId,
  onSelectInstallation,
}: InstallationHealthMapProps) {
  const installationById = new Map(
    installations.map((installation) => [installation.installation_id, installation]),
  )

  return (
    <div className={styles.root}>
      <svg
        aria-label="Installation health map"
        className={styles.map}
        role="img"
        viewBox="0 0 640 360"
      >
        <path
          className={styles.land}
          d="M86 140 L122 112 L188 92 L246 76 L330 86 L388 92 L470 112 L548 150 L572 214 L520 252 L414 282 L300 286 L202 264 L126 220 Z"
        />
        <path
          className={styles.land}
          d="M80 245 L126 232 L176 248 L132 274 L88 270 Z"
        />
        <path
          className={styles.land}
          d="M478 286 L532 278 L578 298 L528 318 L474 310 Z"
        />
        {[120, 220, 320, 420, 520].map((x) => (
          <line className={styles.gridLine} key={`x-${x}`} x1={x} x2={x} y1="58" y2="314" />
        ))}
        {[100, 170, 240].map((y) => (
          <line className={styles.gridLine} key={`y-${y}`} x1="70" x2="582" y1={y} y2={y} />
        ))}
      </svg>

      <div className={styles.markers}>
        {mapPoints.map((point) => {
          const installation = installationById.get(point.installation_id)
          const status = installation?.status ?? point.status
          const openWorkOrders = installation?.open_work_orders ?? 0
          const selected = point.installation_id === selectedInstallationId
          return (
            <button
              aria-pressed={selected}
              aria-label={
                referenceMode
                  ? `Select ${point.name} on map, public reference location, live housing status pending`
                  : `Select ${point.name} on map, ${status} status, ${openWorkOrders} open work orders`
              }
              className={selected ? `${styles.marker} ${styles.markerSelected}` : styles.marker}
              key={point.installation_id}
              onClick={() => onSelectInstallation(point.installation_id)}
              style={{
                ...pointPosition(point.latitude, point.longitude),
                '--marker-color': STATUS_COLOR[status],
                '--marker-size': markerSize(installation, status),
              } as CSSProperties}
              type="button"
            >
              <span className={styles.markerInner} />
            </button>
          )
        })}
      </div>

      <div className={styles.legend} aria-hidden="true">
        {Object.entries(STATUS_COLOR).map(([status, color]) => (
          <span className={styles.legendItem} key={status}>
            <span
              className={styles.legendDot}
              style={{ '--legend-color': color } as CSSProperties}
            />
            {status}
          </span>
        ))}
      </div>
    </div>
  )
}

import type { PackTransport } from '../../api/contracts'
import {
  transportDelta,
  transportValueLabel,
  type ActiveTransport,
} from './transportDelta'
import './configManager.css'

interface TransportWarningProps {
  active: ActiveTransport | null | undefined
  candidate: PackTransport | null | undefined
}

/**
 * States what a transport change costs, before the irreversible click (UXA-404).
 *
 * Renders nothing when the transport is unchanged or unknown — an operator who
 * sees this every time will stop reading it.
 */
export function TransportWarning({ active, candidate }: TransportWarningProps) {
  const delta = transportDelta(active, candidate)
  if (delta.severity === 'none') {
    return null
  }

  return (
    <div
      className="config-manager__transport-warning"
      data-severity={delta.severity}
      data-testid="transport-warning"
      role="alert"
    >
      <strong>This pack changes the event transport.</strong>
      <ul className="config-manager__transport-changes">
        {delta.changes.map((change) => (
          <li key={change.field}>
            <code>{change.field}</code> {transportValueLabel(change.from)} →{' '}
            {transportValueLabel(change.to)}
          </li>
        ))}
      </ul>
      <p>
        {delta.severity === 'decoupled' ? (
          <>
            One side is in-memory. The API and worker are separate processes, so each
            would get its own in-process bus: the API would publish work the worker
            never sees, with no error anywhere. Ingestion and analytics stop.
          </>
        ) : (
          <>
            Work already queued on the current stream has no consumer once the worker
            rebinds, so anything in flight is abandoned. If the new transport is
            unreachable the worker keeps serving the current pack while the API moves
            to the new one.
          </>
        )}
      </p>
    </div>
  )
}

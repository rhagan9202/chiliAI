import { Link } from 'react-router'

import type { EntityLocationResponse } from '../../api/contracts'
import { Card } from '../ui/Card'
import { EmptyState } from '../ui/EmptyState'

interface EntityNotHereProps {
  entityId: string
  /** Knowledge bases that do hold the entity; empty means it exists nowhere. */
  locations: readonly EntityLocationResponse[]
  isResolving: boolean
}

/**
 * What to do when an entity deep link lands on the wrong knowledge base.
 *
 * `/investigation/provider-1` with no `?kb=` resolved against whatever the
 * workspace pointed at and died with "the selected entity could not be
 * loaded" — a generic frame that named neither the cause nor a next step
 * (UXA-104). "It is somewhere else" and "it does not exist" are different
 * answers and get different offers.
 */
export function EntityNotHere({ entityId, locations, isResolving }: EntityNotHereProps) {
  if (isResolving) {
    return (
      <Card>
        <EmptyState
          description={`Checking which knowledge base holds ${entityId}.`}
          title="Looking for this entity"
        />
      </Card>
    )
  }

  const elsewhere = locations[0]

  return (
    <Card>
      {elsewhere ? (
        <EmptyState
          action={
            <Link
              className="page-button page-button--sm page-button--primary"
              to={`/investigation/${encodeURIComponent(entityId)}?kb=${encodeURIComponent(elsewhere.knowledge_base_id)}`}
            >
              {`Switch to ${elsewhere.knowledge_base_name}`}
            </Link>
          }
          description={`${entityId} is not in the knowledge base you are looking at. It is in ${elsewhere.knowledge_base_name}.`}
          title="This entity is in another knowledge base"
        />
      ) : (
        <EmptyState
          action={
            <Link className="page-button page-button--sm" to="/alerts">
              Back to the Alert Feed
            </Link>
          }
          description={`No knowledge base in this workspace holds ${entityId}. The link may be stale, or its knowledge base may have been deleted.`}
          title="This entity no longer exists"
        />
      )}
    </Card>
  )
}

import { Link } from 'react-router-dom'

import styles from './ChatContainer.module.css'

export interface CitationLinkProps {
  entityId: string
  index: number
}

export function CitationLink({ entityId, index }: CitationLinkProps): React.ReactElement {
  return (
    <Link
      to={`/investigation?entity_id=${encodeURIComponent(entityId)}`}
      className={styles.citation}
      data-testid="citation-link"
    >
      [{index + 1}] {entityId}
    </Link>
  )
}

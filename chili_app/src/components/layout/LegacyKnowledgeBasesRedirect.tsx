import { Navigate, useLocation } from 'react-router'

import { KNOWLEDGE_BASES_ROUTE } from '../../utils/knowledgeBaseRoutes'

/**
 * Sends the pre-split `/knowledgebases` address on with its query string intact.
 *
 * That query string carried the knowledge base (`?kb=`), so the bare
 * `<Navigate to="/knowledge-bases">` this replaces dropped it and sent every
 * old bookmark to whichever corpus the page happened to auto-select. The
 * library resolves the `?kb=` into a workspace address from there, so neither
 * hop needs to know about the other.
 */
export function LegacyKnowledgeBasesRedirect(): React.ReactElement {
  const { search } = useLocation()
  return <Navigate replace to={`${KNOWLEDGE_BASES_ROUTE}${search}`} />
}

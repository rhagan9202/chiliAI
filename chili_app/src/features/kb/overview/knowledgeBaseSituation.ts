import type { KnowledgeBaseSummaryResponse } from '../../../api/contracts'
import { countLabel } from '../../../utils/countLabel'

/**
 * One sentence about where this knowledge base actually stands.
 *
 * Not a status word: the three states a corpus is genuinely in — nothing in
 * it, something in it that produced nothing, something in it that answers
 * questions — need different next actions, and the sentence is what tells them
 * apart before the buttons do.
 */
export function knowledgeBaseSituation(knowledgeBase: KnowledgeBaseSummaryResponse): string {
  if (knowledgeBase.document_count === 0 && knowledgeBase.entity_count === 0) {
    return 'This knowledge base is empty. Add documents or structured records to start.'
  }
  if (knowledgeBase.entity_count === 0) {
    const verb = knowledgeBase.document_count === 1 ? 'is' : 'are'
    return `${countLabel(knowledgeBase.document_count, 'document')} ${verb} ingested but produced no entities yet. Check the runs for extraction problems.`
  }
  return `${countLabel(knowledgeBase.entity_count, 'entity', 'entities')} and ${countLabel(
    knowledgeBase.relationship_count,
    'relationship',
  )} from ${countLabel(knowledgeBase.document_count, 'document')} are ready to investigate.`
}

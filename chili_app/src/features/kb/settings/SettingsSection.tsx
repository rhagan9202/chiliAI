import { useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router'

import type { WorkspaceOutletContext } from '../../../pages/KnowledgeBaseWorkspacePage'
import { KNOWLEDGE_BASES_ROUTE } from '../../../utils/knowledgeBaseRoutes'
import type { KnowledgeBaseSummaryResponse } from '../../../api/contracts'
import { useDeleteKnowledgeBase } from '../../../api/knowledgebases'
import { ConfirmDialog } from '../../../components/status/ConfirmDialog'
import { formatTimestamp } from '../../../components/status/formatters'
import { Card } from '../../../components/ui/Card'
import { useIngestionDraftStore } from '../../../stores/ingestionDraftStore'
import { countLabel } from '../../../utils/countLabel'
import '../kb.css'

type SettingsSectionProps = {
  knowledgeBase: KnowledgeBaseSummaryResponse
  /** Called after the knowledge base is gone; the workspace it named is too. */
  onDeleted: () => void
}

export function SettingsSection({ knowledgeBase, onDeleted }: SettingsSectionProps) {
  const [confirming, setConfirming] = useState(false)
  const clearDraft = useIngestionDraftStore((state) => state.clearDraft)
  const deleteMutation = useDeleteKnowledgeBase()

  return (
    <>
      <Card>
        <section aria-labelledby="kb-settings-details">
          <h2 id="kb-settings-details">Details</h2>
          {/* Ids and raw timestamps are reference material, not part of the
              working flow — §3c demotes them to a details row like this one. */}
          <dl className="kb-settings__details">
            <dt>Knowledge base id</dt>
            <dd><code>{knowledgeBase.id}</code></dd>
            <dt>Domain</dt>
            <dd>{knowledgeBase.domain ?? 'Not stamped'}</dd>
            <dt>Created</dt>
            <dd>{formatTimestamp(knowledgeBase.created_at)}</dd>
            <dt>Last updated</dt>
            <dd>{formatTimestamp(knowledgeBase.updated_at ?? null)}</dd>
          </dl>
        </section>
      </Card>

      <Card>
        <section aria-labelledby="kb-settings-danger">
          <h2 id="kb-settings-danger">Delete this knowledge base</h2>
          <p className="page-copy-block">
            Deleting removes the corpus and everything derived from it. There is no undo and
            no export.
          </p>
          <button
            className="page-button page-button--secondary"
            disabled={deleteMutation.isPending}
            onClick={() => setConfirming(true)}
            type="button"
          >
            Delete knowledge base
          </button>
        </section>
      </Card>

      <ConfirmDialog
        body={`Deletes ${countLabel(knowledgeBase.document_count, 'document')}, ${countLabel(
          knowledgeBase.entity_count,
          'entity',
          'entities',
        )}, ${countLabel(
          knowledgeBase.relationship_count,
          'relationship',
        )}, and every run recorded against it. This cannot be undone.`}
        confirmLabel="Delete knowledge base"
        confirmTypedText={knowledgeBase.name}
        destructive
        onCancel={() => setConfirming(false)}
        onConfirm={() => {
          setConfirming(false)
          deleteMutation.mutate(knowledgeBase.id, {
            onSuccess: () => {
              // Its draft has nowhere to submit to now.
              clearDraft(knowledgeBase.id)
              onDeleted()
            },
          })
        }}
        open={confirming}
        title="Delete knowledge base"
      />
    </>
  )
}

/**
 * Route binding for `/knowledge-bases/:kbId/settings`. Deleting the knowledge
 * base deletes the address it was read at, so the library is the only place
 * left to be.
 */
export function SettingsRoute() {
  const navigate = useNavigate()
  const { knowledgeBase } = useOutletContext<WorkspaceOutletContext>()
  return (
    <SettingsSection
      knowledgeBase={knowledgeBase}
      onDeleted={() => {
        navigate(KNOWLEDGE_BASES_ROUTE, { replace: true })
      }}
    />
  )
}

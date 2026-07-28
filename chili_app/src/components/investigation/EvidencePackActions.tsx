import { useState } from 'react'

import { exportEvidencePack } from '../../api/evidence'
import type { EvidenceExportFormat } from '../../api/contracts'
import { showToast } from '../common/toastStore'
import { downloadTextFile, EXPORT_MIME_TYPES } from '../../utils/downloadFile'
import './investigation.css'

interface EvidencePackActionsProps {
  evidencePackId: string
  knowledgeBaseId: string
  /**
   * Cases this alert could be attached to. Omit entirely where there is no
   * alert in hand — the workbench shows a pack without one, and offering to
   * attach there would mean inventing an alert (UXA-405).
   */
  attach?: {
    alertId: string
    /** Only what the picker needs: the generated list type leaves `alert_ids`
        optional, and demanding the whole response would couple this component
        to fields it never reads. */
    cases: readonly { id: string; title: string; alert_ids?: string[] }[]
    isPending: boolean
    onAttach: (caseId: string) => void
  }
}

/**
 * Give the evidence pack an outward path: download it, or add its alert to a
 * case that already exists (UXA-405).
 *
 * The pack is the product's core explainability artifact and could not leave
 * the browser, nor reach any case except by opening a new one.
 */
export function EvidencePackActions({
  evidencePackId,
  knowledgeBaseId,
  attach,
}: EvidencePackActionsProps) {
  const [exporting, setExporting] = useState<EvidenceExportFormat | null>(null)
  const [picking, setPicking] = useState(false)

  const handleExport = async (format: EvidenceExportFormat) => {
    setExporting(format)
    try {
      const payload = await exportEvidencePack(evidencePackId, knowledgeBaseId, format)
      downloadTextFile(payload.filename, payload.content, EXPORT_MIME_TYPES[payload.format])
    } catch {
      showToast('error', 'Could not export this evidence pack.')
    } finally {
      setExporting(null)
    }
  }

  // Attaching an alert twice is refused by the API; excluding those cases here
  // means the analyst never sees an option that would fail.
  const eligible = attach
    ? attach.cases.filter((item) => !(item.alert_ids ?? []).includes(attach.alertId))
    : []

  return (
    <>
      {attach ? (
        picking ? (
          <div className="evidence-attach" data-testid="evidence-attach-picker">
            {eligible.length > 0 ? (
              <>
                <label className="filter-group__label" htmlFor="evidence-attach-case">
                  Attach to
                </label>
                <select
                  className="page-input--inline"
                  disabled={attach.isPending}
                  id="evidence-attach-case"
                  onChange={(event) => {
                    if (event.target.value) {
                      attach.onAttach(event.target.value)
                      setPicking(false)
                    }
                  }}
                  defaultValue=""
                >
                  <option disabled value="">
                    Choose a case…
                  </option>
                  {eligible.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.title}
                    </option>
                  ))}
                </select>
              </>
            ) : (
              <span className="metric-row__label">
                {attach.cases.length === 0
                  ? 'No cases yet — promote this alert to open the first one.'
                  : 'Every open case already holds this alert.'}
              </span>
            )}
            <button
              className="page-button page-button--sm page-button--secondary"
              onClick={() => setPicking(false)}
              type="button"
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            className="page-button page-button--sm page-button--secondary"
            disabled={attach.isPending}
            onClick={() => setPicking(true)}
            type="button"
          >
            {attach.isPending ? 'Attaching…' : 'Attach to case'}
          </button>
        )
      ) : null}
      <button
        className="page-button page-button--sm page-button--secondary"
        disabled={exporting !== null}
        onClick={() => void handleExport('markdown')}
        type="button"
      >
        {exporting === 'markdown' ? 'Exporting…' : 'Export Markdown'}
      </button>
      <button
        className="page-button page-button--sm page-button--secondary"
        disabled={exporting !== null}
        onClick={() => void handleExport('json')}
        type="button"
      >
        {exporting === 'json' ? 'Exporting…' : 'Export JSON'}
      </button>
    </>
  )
}

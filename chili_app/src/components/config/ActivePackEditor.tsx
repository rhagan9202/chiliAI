import { useMemo, useRef, useState } from 'react'
import { EditorSelection } from '@codemirror/state'
import { EditorView } from '@codemirror/view'
import { stringify as stringifyYaml } from 'yaml'

import { useApplyPack, useDomainConfig, useValidatePack } from '../../api/config'
import type { ConfigSwapResponse, ValidatePackResponse } from '../../api/contracts'
import { Card } from '../ui/Card'
import { ErrorState } from '../ui/ErrorState'
import { LoadingState } from '../ui/LoadingState'
import { SwapResultBanner } from './SwapResultBanner'
import { TransportWarning } from './TransportWarning'
import { YamlEditor } from './YamlEditor'
import styles from './YamlEditor.module.css'
import { locateInYaml, parseBufferToContent } from './packYaml'
import './configManager.css'

interface ValidationOutcome {
  /** Exact buffer text the outcome belongs to — edits invalidate it. */
  buffer: string
  result: ValidatePackResponse
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error) {
    return error.message
  }
  return fallback
}

export function ActivePackEditor() {
  const domainConfig = useDomainConfig()
  const validateMutation = useValidatePack()
  const applyMutation = useApplyPack()

  // null = pristine buffer mirroring the active config; a string = edited.
  const [buffer, setBuffer] = useState<string | null>(null)
  const [validation, setValidation] = useState<ValidationOutcome | null>(null)
  const [lastSwap, setLastSwap] = useState<ConfigSwapResponse | null>(null)
  const viewRef = useRef<EditorView | null>(null)

  const seededYaml = useMemo(
    () => (domainConfig.data ? stringifyYaml(domainConfig.data) : ''),
    [domainConfig.data],
  )
  const editorValue = buffer ?? seededYaml

  if (domainConfig.isLoading) {
    return <LoadingState label="Loading the active pack" />
  }

  if (domainConfig.isError) {
    return <ErrorState description="The active domain configuration could not be loaded, so the pack editor is unavailable." />
  }

  const bufferValidated =
    validation !== null && validation.buffer === editorValue && validation.result.valid
  const validationErrors =
    validation !== null && validation.buffer === editorValue
      ? validation.result.errors
      : []

  const handleChange = (next: string) => {
    setBuffer(next)
  }

  /**
   * Select the value an issue points at and scroll it into view (UXA-404).
   *
   * The dotted `field` path told an operator *what* was wrong; it did not tell
   * them where in a 600-line pack to look.
   */
  const revealIssue = (loc: readonly string[]) => {
    const view = viewRef.current
    if (!view) {
      return
    }
    const range = locateInYaml(editorValue, loc)
    if (!range) {
      return
    }
    view.dispatch({
      selection: EditorSelection.range(range.from, range.to),
      effects: EditorView.scrollIntoView(range.from, { y: 'center' }),
      scrollIntoView: true,
    })
    view.focus()
  }

  const handleValidate = () => {
    setLastSwap(null)
    const parsed = parseBufferToContent(editorValue)
    if ('issue' in parsed) {
      setValidation({
        buffer: editorValue,
        result: { valid: false, errors: [parsed.issue] },
      })
      return
    }
    validateMutation.mutate(
      { content: parsed.content },
      {
        onSuccess: (result) => {
          setValidation({ buffer: editorValue, result })
        },
      },
    )
  }

  const handleApply = () => {
    applyMutation.mutate(
      {},
      {
        onSuccess: (result) => {
          setLastSwap(result)
          // The active config changed; drop local edit state so the editor
          // reseeds from the freshly refetched domain config.
          setBuffer(null)
          setValidation(null)
        },
      },
    )
  }

  return (
    <Card>
      <div className="config-manager__editor" data-testid="active-pack-editor">
        <p className={styles.deviationNote}>
          Check runs your edit against the full pack definition and reports what would break.
          Apply re-reads the pack from disk and puts it into effect — edits made here in the
          browser are not saved.
        </p>
        <YamlEditor
          ariaLabel="Active domain pack editor"
          onChange={handleChange}
          onReady={(view) => {
            viewRef.current = view
          }}
          value={editorValue}
        />
        <div className={styles.toolbar}>
          <button
            className={styles.button}
            disabled={validateMutation.isPending || editorValue.trim().length === 0}
            onClick={handleValidate}
            type="button"
          >
            {validateMutation.isPending ? 'Validating…' : 'Validate'}
          </button>
          <button
            className={`${styles.button} ${styles.primary}`}
            disabled={!bufferValidated || applyMutation.isPending}
            onClick={handleApply}
            title={
              bufferValidated
                ? 'Re-validate and re-apply the active pack'
                : 'Validate the current buffer before applying'
            }
            type="button"
          >
            {applyMutation.isPending ? 'Applying…' : 'Apply'}
          </button>
          <button
            className={styles.button}
            disabled={buffer === null}
            onClick={() => {
              setBuffer(null)
              setValidation(null)
            }}
            type="button"
          >
            Reset to active config
          </button>
          {bufferValidated ? (
            <span className={styles.statusOk} data-testid="validate-success" role="status">
              Valid pack
              {validation?.result.display_name ? `: ${validation.result.display_name}` : ''}
            </span>
          ) : null}
        </div>
        {/* Only meaningful once the buffer validated — an invalid pack reports
            no transport to compare (UXA-404). */}
        {bufferValidated ? (
          <TransportWarning
            active={domainConfig.data?.events}
            candidate={validation?.result.transport}
          />
        ) : null}
        {validationErrors.length > 0 ? (
          <ul className="config-manager__issues" data-testid="validation-issues" role="alert">
            {validationErrors.map((issue, index) => {
              // A file-level issue carries no path, and the buffer may have been
              // edited since it was validated — neither gets a dead control.
              const locatable =
                issue.field !== '' && locateInYaml(editorValue, issue.loc ?? []) !== null
              return (
                <li className="config-manager__issue" key={`${issue.field}-${index}`}>
                  {issue.field ? (
                    locatable ? (
                      <button
                        className="config-manager__issue-field config-manager__issue-field--link"
                        onClick={() => revealIssue(issue.loc ?? [])}
                        title="Show this field in the editor"
                        type="button"
                      >
                        {issue.field}
                      </button>
                    ) : (
                      <code className="config-manager__issue-field">{issue.field}</code>
                    )
                  ) : null}
                  <span>{issue.message}</span>
                  <span className="config-manager__issue-type">{issue.error_type}</span>
                </li>
              )
            })}
          </ul>
        ) : null}
        {validateMutation.isError ? (
          <p className="config-manager__error" role="alert">
            {errorMessage(validateMutation.error, 'Validation request failed.')}
          </p>
        ) : null}
        {applyMutation.isError ? (
          <p className="config-manager__error" role="alert">
            {errorMessage(applyMutation.error, 'Apply failed; the active configuration is unchanged.')}
          </p>
        ) : null}
        {lastSwap ? <SwapResultBanner result={lastSwap} /> : null}
      </div>
    </Card>
  )
}

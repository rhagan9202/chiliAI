import { useMemo, useState } from 'react'
import { stringify as stringifyYaml } from 'yaml'

import { useApplyPack, useDomainConfig, useValidatePack } from '../../api/config'
import type { ConfigSwapResponse, ValidatePackResponse } from '../../api/contracts'
import { Card } from '../ui/Card'
import { ErrorState } from '../ui/ErrorState'
import { LoadingState } from '../ui/LoadingState'
import { SwapResultBanner } from './SwapResultBanner'
import { YamlEditor } from './YamlEditor'
import styles from './YamlEditor.module.css'
import { parseBufferToContent } from './packYaml'
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
          Edits here are dry-run validated against the full domain-pack schema. Apply re-validates
          and re-applies the active pack from disk and hot-swaps the workspace — it does not
          persist browser-side edits.
        </p>
        <YamlEditor
          ariaLabel="Active domain pack editor"
          onChange={handleChange}
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
        {validationErrors.length > 0 ? (
          <ul className="config-manager__issues" data-testid="validation-issues" role="alert">
            {validationErrors.map((issue, index) => (
              <li className="config-manager__issue" key={`${issue.field}-${index}`}>
                {issue.field ? (
                  <code className="config-manager__issue-field">{issue.field}</code>
                ) : null}
                <span>{issue.message}</span>
                <span className="config-manager__issue-type">{issue.error_type}</span>
              </li>
            ))}
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

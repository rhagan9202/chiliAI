import { useEffect, useState } from 'react'

import { YamlEditor } from '../components/config/YamlEditor'
import styles from '../components/config/YamlEditor.module.css'
import { useDomainConfigYaml } from '../hooks/useDomainConfigYaml'

// Save endpoint (PUT /config/domain) is not yet implemented on the backend.
// Per the story prompt the Save button is disabled with a tooltip until
// the backend ships it. Reset re-fetches the active config from
// `GET /config/domain`.
const SAVE_DISABLED_REASON =
  'save endpoint not yet available — PUT /config/domain pending backend story E5-S09'

export function ConfigEditor(): React.ReactElement {
  const { text, config, loading, error, reload } = useDomainConfigYaml()
  const [draft, setDraft] = useState<string>('')
  const [resetting, setResetting] = useState<boolean>(false)
  const [resetError, setResetError] = useState<Error | null>(null)

  useEffect(() => {
    setDraft(text)
  }, [text])

  const dirty = draft !== text

  const onReset = async (): Promise<void> => {
    setResetting(true)
    setResetError(null)
    try {
      await reload()
    } catch (err: unknown) {
      setResetError(err instanceof Error ? err : new Error(String(err)))
    } finally {
      setResetting(false)
    }
  }

  return (
    <section
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        height: '100%',
        minHeight: 480,
      }}
    >
      <header>
        <h1>Configuration Editor</h1>
        <p style={{ marginTop: 0 }}>
          Active domain:{' '}
          <strong>{config?.domain.display_name ?? '—'}</strong>
        </p>
      </header>

      <div className={styles.toolbar}>
        <button
          type="button"
          className={`${styles.button} ${styles.primary}`}
          disabled
          title={SAVE_DISABLED_REASON}
          aria-disabled="true"
          data-testid="save-config"
        >
          Save
        </button>
        <button
          type="button"
          className={styles.button}
          disabled={loading || resetting}
          onClick={() => {
            void onReset()
          }}
          data-testid="reset-config"
        >
          {resetting ? 'Resetting…' : 'Reset to defaults'}
        </button>
        {loading ? (
          <span className={styles.statusBusy}>Loading config…</span>
        ) : null}
        {!loading && !dirty && !error ? (
          <span className={styles.statusOk}>Up to date</span>
        ) : null}
      </div>

      <p className={styles.deviationNote}>
        Note: configuration is shown as pretty-printed JSON with YAML syntax
        highlighting. A YAML serializer is intentionally not bundled.
      </p>

      {error ? (
        <div className={styles.errorBox} role="alert" data-testid="config-error">
          Failed to load configuration: {error.message}
        </div>
      ) : null}
      {resetError ? (
        <div className={styles.errorBox} role="alert">
          Reset failed: {resetError.message}
        </div>
      ) : null}

      <div className={styles.editorWrap}>
        <YamlEditor
          value={draft}
          onChange={setDraft}
          readOnly={loading || config === null}
        />
      </div>
    </section>
  )
}

export default ConfigEditor

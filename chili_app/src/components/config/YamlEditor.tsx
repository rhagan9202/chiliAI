import { useMemo } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { yaml } from '@codemirror/lang-yaml'
import type { Extension } from '@codemirror/state'
import type { EditorView } from '@codemirror/view'

import styles from './YamlEditor.module.css'

export interface YamlEditorProps {
  value: string
  onChange: (next: string) => void
  readOnly?: boolean
  ariaLabel?: string
  /**
   * Hands the live editor view to the caller so it can drive a selection —
   * used to reveal the line a validation issue points at (UXA-404).
   */
  onReady?: (view: EditorView) => void
}

export function YamlEditor({
  value,
  onChange,
  readOnly = false,
  ariaLabel = 'Domain configuration editor',
  onReady,
}: YamlEditorProps): React.ReactElement {
  const extensions = useMemo<Extension[]>(() => [yaml()], [])

  return (
    <div className={styles.editor} data-testid="yaml-editor">
      <CodeMirror
        value={value}
        extensions={extensions}
        onChange={onChange}
        onCreateEditor={(view) => onReady?.(view)}
        readOnly={readOnly}
        basicSetup={{
          lineNumbers: true,
          foldGutter: true,
          highlightActiveLine: true,
        }}
        aria-label={ariaLabel}
        height="100%"
      />
    </div>
  )
}

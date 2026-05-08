import { useMemo } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { yaml } from '@codemirror/lang-yaml'
import type { Extension } from '@codemirror/state'

import styles from './YamlEditor.module.css'

export interface YamlEditorProps {
  value: string
  onChange: (next: string) => void
  readOnly?: boolean
  ariaLabel?: string
}

export function YamlEditor({
  value,
  onChange,
  readOnly = false,
  ariaLabel = 'Domain configuration editor',
}: YamlEditorProps): React.ReactElement {
  const extensions = useMemo<Extension[]>(() => [yaml()], [])

  return (
    <div className={styles.editor} data-testid="yaml-editor">
      <CodeMirror
        value={value}
        extensions={extensions}
        onChange={onChange}
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

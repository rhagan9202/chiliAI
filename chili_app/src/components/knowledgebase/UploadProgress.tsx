import styles from './DropZone.module.css'

export interface UploadProgressProps {
  filename: string
  percent: number
}

export function UploadProgress({
  filename,
  percent,
}: UploadProgressProps): React.ReactElement {
  const safePercent = Math.max(0, Math.min(100, percent))
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={safePercent}
      aria-label={`Uploading ${filename}`}
      data-testid="upload-progress"
      style={{ marginTop: 12 }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 13,
          color: 'var(--text, #6b6375)',
          marginBottom: 4,
        }}
      >
        <span>{filename}</span>
        <span>{safePercent}%</span>
      </div>
      <div className={styles.progress}>
        <div
          className={styles.progressBar}
          style={{ width: `${safePercent}%` }}
        />
      </div>
    </div>
  )
}

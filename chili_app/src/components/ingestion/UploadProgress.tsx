import './ingestion.css'

export type UploadStatus = 'idle' | 'uploading' | 'error' | 'done'

type UploadProgressProps = {
  /** Accessible label describing what is being uploaded. */
  label: string
  status: UploadStatus
  /** Upload completion percentage (0-100). */
  percent: number
  /** Error message to surface when the upload failed. */
  error?: string
  onRetry: () => void
}

/**
 * Renders byte-level upload progress for an in-flight ingestion upload, plus an
 * error state with a retry affordance. Renders nothing when idle and clean so
 * it can be mounted unconditionally beside the submit controls.
 */
export function UploadProgress({ label, status, percent, error, onRetry }: UploadProgressProps) {
  if (status === 'idle' || status === 'done') {
    return null
  }

  const clamped = Math.max(0, Math.min(100, Math.round(percent)))

  return (
    <div className="ingestion-upload-progress" aria-live="polite">
      {status === 'uploading' ? (
        <div className="ingestion-upload-progress__track-row">
          <div
            className="ingestion-upload-progress__track"
            role="progressbar"
            aria-label={label}
            aria-valuenow={clamped}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div
              className="ingestion-upload-progress__bar"
              style={{ width: `${clamped}%` }}
            />
          </div>
          <span className="ingestion-upload-progress__percent">{clamped}%</span>
        </div>
      ) : null}

      {status === 'error' ? (
        <div className="ingestion-upload-progress__error">
          <p className="ingestion-upload-progress__message" role="alert">
            {error ?? 'Upload failed. Please try again.'}
          </p>
          <button
            className="page-button page-button--secondary"
            type="button"
            onClick={onRetry}
          >
            Retry upload
          </button>
        </div>
      ) : null}
    </div>
  )
}

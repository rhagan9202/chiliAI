/**
 * The single home for timestamp and file-size rendering.
 *
 * Before this module the page carried three private date formatters, two file
 * size helpers, and two panels that printed raw ISO strings straight from the
 * API. Timelines want relative time ("4m ago"); everything else wants an
 * absolute local instant. Both live here so the vocabulary cannot drift again.
 */
const absoluteFormat = new Intl.DateTimeFormat('en-US', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return 'Not yet recorded'
  }
  return absoluteFormat.format(new Date(value))
}

/** Relative time for timelines: "just now" / "16m ago" / "3h ago", absolute beyond 24h. */
export function formatRelativeTime(
  value: string | null | undefined,
  now: Date = new Date(),
): string {
  if (!value) {
    return 'Not yet recorded'
  }
  const elapsedMs = now.getTime() - new Date(value).getTime()
  const minutes = Math.floor(elapsedMs / 60_000)
  if (minutes < 1) {
    return 'just now'
  }
  if (minutes < 60) {
    return `${minutes}m ago`
  }
  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    return `${hours}h ago`
  }
  return formatTimestamp(value)
}

export function formatFileSize(sizeBytes: number | null | undefined): string {
  if (!sizeBytes) {
    return 'Unknown size'
  }
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`
  }
  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`
  }
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`
}

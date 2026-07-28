/**
 * Save text the browser already has as a file.
 *
 * Lifted out of `ScorecardRunPage.tsx` when the evidence pack gained an export
 * (UXA-405) — two callers, one implementation. Both exports arrive as a
 * `{ filename, content }` payload from the API, so the only browser-side work
 * is handing it to a download.
 *
 * The object URL is revoked immediately: the anchor click is synchronous, so
 * holding the blob past it only leaks.
 */
export function downloadTextFile(
  filename: string,
  content: string,
  mimeType: string,
): void {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

/** MIME type for an export format the API can return. */
export const EXPORT_MIME_TYPES = {
  json: 'application/json',
  markdown: 'text/markdown',
} as const

/**
 * Poll a knowledge base's document list for one document's warnings to land,
 * against the real API rather than the DOM.
 *
 * `warning_count`/`warning_reasons` land as soon as the parse stage finishes
 * (confirmed against the real stack: a plain CSV upload reaches them in ~2s
 * and they never change afterwards, independent of whatever the document's
 * broader lifecycle status is doing) — waiting for those fields directly is
 * both faster and closer to the actual condition the UI's warning chip
 * depends on than waiting for the document to reach some particular
 * `current_status`. Polling the API also fails immediately when the document
 * reaches `failed`, surfacing `last_error` instead of a bare DOM timeout.
 */
type DocumentSnapshot = {
  filename: string
  current_status?: string | null
  status?: string | null
  warning_count?: number | null
  warning_reasons?: string[] | null
  last_error?: string | null
}

export async function waitForDocumentWarnings(
  api: string,
  knowledgeBaseId: string,
  filename: string,
  timeoutMs = 120_000,
): Promise<DocumentSnapshot> {
  const deadline = Date.now() + timeoutMs
  let last: DocumentSnapshot | null = null

  while (Date.now() < deadline) {
    const res = await fetch(`${api}/knowledgebases/${knowledgeBaseId}/documents`)
    if (res.ok) {
      const body = (await res.json()) as { items?: DocumentSnapshot[]; documents?: DocumentSnapshot[] }
      const items = body.items ?? body.documents ?? []
      const doc = items.find((item) => item.filename === filename)
      if (doc) {
        last = doc
        const status = doc.current_status ?? doc.status ?? 'pending'
        if (status === 'failed') {
          throw new Error(
            `document "${filename}" in knowledge base ${knowledgeBaseId} failed ingestion: ${
              doc.last_error ?? '(no last_error reported)'
            }`,
          )
        }
        if ((doc.warning_count ?? 0) > 0) {
          return doc
        }
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }

  throw new Error(
    `document "${filename}" in knowledge base ${knowledgeBaseId} reported no warnings within ` +
      `${timeoutMs}ms (last seen: ${JSON.stringify(last)}). The worker is a single shared ` +
      'consumer, so this can mean it is still queued behind other work rather than stuck — check ' +
      '`docker compose logs worker` for the real state before assuming a regression.',
  )
}

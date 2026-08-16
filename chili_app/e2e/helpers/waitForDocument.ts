/**
 * Poll a knowledge base's document list for a real backend condition on one
 * document, rather than a bare DOM timeout.
 *
 * The already-mounted Data page's document query
 * (`useKnowledgeBaseDocuments`) has no polling interval — it refreshes only
 * via the realtime SSE stream's coarse, KB-status-level invalidation or a
 * fresh fetch. Confirmed twice against the real stack (a plain CSV upload,
 * and a two-file documents submission that includes a zero-entity document):
 * the backend finishes and the API reflects it correctly within ~2 seconds
 * on an idle stack, independent of whatever an already-open page's query
 * happens to be showing. Waiting on the API directly, rather than the DOM,
 * both fails fast (with `last_error`) if a document genuinely reaches
 * `failed`, and avoids the open question of exactly when/whether the
 * realtime stream's invalidation lands for an already-mounted page.
 */
type DocumentSnapshot = {
  filename: string
  current_status?: string | null
  status?: string | null
  warning_count?: number | null
  warning_reasons?: string[] | null
  last_error?: string | null
}

async function pollDocument(
  api: string,
  knowledgeBaseId: string,
  filename: string,
  timeoutMs: number,
  isDone: (doc: DocumentSnapshot) => boolean,
  describeCondition: string,
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
        if (isDone(doc)) {
          return doc
        }
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }

  throw new Error(
    `document "${filename}" in knowledge base ${knowledgeBaseId} did not reach ${describeCondition} ` +
      `within ${timeoutMs}ms (last seen: ${JSON.stringify(last)}). The worker is a single shared ` +
      'consumer, so this can mean it is still queued behind other work rather than stuck — check ' +
      '`docker compose logs worker` for the real state before assuming a regression.',
  )
}

/**
 * `warning_count`/`warning_reasons` land as soon as the parse stage
 * finishes, independent of whatever `current_status` the document's broader
 * lifecycle is otherwise reporting — waiting for those fields directly is
 * both faster and closer to the actual condition the UI's warning chip
 * depends on.
 */
export function waitForDocumentWarnings(
  api: string,
  knowledgeBaseId: string,
  filename: string,
  timeoutMs = 120_000,
): Promise<DocumentSnapshot> {
  return pollDocument(
    api,
    knowledgeBaseId,
    filename,
    timeoutMs,
    (doc) => (doc.warning_count ?? 0) > 0,
    'a nonzero warning_count',
  )
}

/** Waits for a document's `current_status` to reach one of `terminalStatuses`. */
export function waitForDocumentStatus(
  api: string,
  knowledgeBaseId: string,
  filename: string,
  terminalStatuses: readonly string[],
  timeoutMs = 120_000,
): Promise<DocumentSnapshot> {
  return pollDocument(
    api,
    knowledgeBaseId,
    filename,
    timeoutMs,
    (doc) => terminalStatuses.includes(doc.current_status ?? doc.status ?? 'pending'),
    `one of [${terminalStatuses.join(', ')}]`,
  )
}

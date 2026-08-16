/**
 * Best-effort, retrying DELETE for a knowledge base a spec created.
 *
 * A knowledge base whose ingestion (or a score run it triggered) is still in
 * flight rejects DELETE with 409 ("workflow in progress") — a correct guard,
 * not a failure. global-teardown.ts eventually reclaims anything a spec
 * leaves behind, but each spec is still responsible for cleaning up after
 * itself rather than leaning on that net, so this retries with backoff
 * instead of giving up on the first 409.
 */
export async function deleteKnowledgeBase(api: string, knowledgeBaseId: string): Promise<void> {
  let lastStatus = 0
  for (let attempt = 0; attempt < 8; attempt += 1) {
    if (attempt > 0) {
      await new Promise((resolve) => setTimeout(resolve, 3000))
    }
    const res = await fetch(`${api}/knowledgebases/${encodeURIComponent(knowledgeBaseId)}`, {
      method: 'DELETE',
    })
    if (res.ok) {
      return
    }
    lastStatus = res.status
    if (res.status !== 409) {
      break
    }
  }
  console.warn(
    `[e2e] could not delete knowledge base ${knowledgeBaseId} (last status ${lastStatus}); ` +
      'global-teardown will reclaim it',
  )
}

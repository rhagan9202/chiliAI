/**
 * Shared contract between global-setup.ts (writes the pre-run knowledge base
 * snapshot) and global-teardown.ts (deletes every KB created after it), plus
 * the baseline-diff deletion both of them run: teardown at the end of a run,
 * setup against a STALE baseline left behind by a run that never reached
 * teardown (crash, Ctrl-C, system hang). Without the setup-side reclaim, the
 * next run's fresh snapshot would adopt the leaked KBs as "pre-existing" and
 * grandfather them in forever.
 */

export const KB_BASELINE_PATH = 'e2e/.kb-baseline.json'

export type KbBaseline = {
  captured_at: string
  knowledge_base_ids: string[]
}

export type KbCleanupResult = {
  deleted: number
  failed: number
}

/**
 * Delete every KB on the stack that is not in the baseline, through the real
 * DELETE /knowledgebases/{id} endpoint so the backend's full cleanup cascade
 * (documents, records, observations, scorecard runs, alert projections)
 * applies. Pre-existing KBs are never touched.
 */
export async function deleteKbsNotInBaseline(
  api: string,
  baseline: KbBaseline,
  logPrefix: string,
): Promise<KbCleanupResult> {
  const preExisting = new Set(baseline.knowledge_base_ids)

  const res = await fetch(`${api}/knowledgebases`)
  if (!res.ok) {
    console.warn(`${logPrefix} GET /knowledgebases failed (${res.status}) — skipping KB cleanup`)
    return { deleted: 0, failed: 0 }
  }
  const payload = (await res.json()) as { items: { id: string; name: string }[] }
  const created = payload.items.filter((kb) => !preExisting.has(kb.id))

  let failed = 0
  for (const kb of created) {
    const del = await fetch(`${api}/knowledgebases/${encodeURIComponent(kb.id)}`, {
      method: 'DELETE',
    })
    if (del.ok) {
      console.log(`${logPrefix} deleted KB "${kb.name}" (${kb.id})`)
    } else {
      failed += 1
      console.error(
        `${logPrefix} FAILED to delete KB "${kb.name}" (${kb.id}): ${del.status} ${await del
          .text()
          .catch(() => '')}`,
      )
    }
  }
  return { deleted: created.length - failed, failed }
}

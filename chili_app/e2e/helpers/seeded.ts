/**
 * Loader for the deterministic ids seeded by global-setup.ts via /admin/dev-seed.
 * Specs read real backend data scoped to these ids.
 */

import { readFileSync } from 'node:fs'

export type SeededIds = {
  knowledge_base_id: string
  entity_id: string
  alert_id: string
  evidence_pack_id: string
  case_id: string
  policy_item_id: string
}

let cached: SeededIds | null = null

export function seeded(): SeededIds {
  if (cached === null) {
    cached = JSON.parse(readFileSync('e2e/.seeded.json', 'utf-8')) as SeededIds
  }
  return cached
}

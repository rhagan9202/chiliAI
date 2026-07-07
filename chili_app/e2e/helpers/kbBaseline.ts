/**
 * Shared contract between global-setup.ts (writes the pre-run knowledge base
 * snapshot) and global-teardown.ts (deletes every KB created after it).
 */

export const KB_BASELINE_PATH = 'e2e/.kb-baseline.json'

export type KbBaseline = {
  captured_at: string
  knowledge_base_ids: string[]
}

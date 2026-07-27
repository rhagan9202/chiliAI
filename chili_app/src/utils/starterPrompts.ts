import type { DomainConfig } from '../api/contracts'

/**
 * Opening questions for an empty conversation, derived from the active pack
 * (UXA-403).
 *
 * An empty chat box against an unfamiliar corpus is the hardest possible
 * starting point. These are built from the pack's own entity and relationship
 * labels rather than hardcoded fraud wording, so switching domains changes the
 * suggestions with no frontend change — the same promise as nav and labels.
 */

/** Four fits the empty state without turning it into a menu. */
const MAX_PROMPTS = 4

export function starterPrompts(config: DomainConfig | null): string[] {
  if (config === null) return []

  const entities = config.entities ?? []
  const relationships = config.relationships ?? []
  const [primary, secondary] = entities
  const relationship = relationships[0]

  const prompts: string[] = []
  if (primary) {
    prompts.push(`Which ${primary.display_label} records look most unusual, and why?`)
    prompts.push(`Summarize what is known about a single ${primary.display_label}.`)
  }
  if (relationship) {
    prompts.push(
      `Show the "${relationship.display_label}" connections and what stands out about them.`,
    )
  }
  if (secondary) {
    prompts.push(`What patterns link ${primary?.display_label} and ${secondary.display_label}?`)
  }

  return prompts.slice(0, MAX_PROMPTS)
}

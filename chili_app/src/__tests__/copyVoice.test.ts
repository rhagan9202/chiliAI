import { describe, expect, it } from 'vitest'

import { collectCopyCandidates, collectUserFacingCopy } from '../test-utils/userFacingCopy'

/**
 * The audit's most pervasive finding (UXA-301) was that user-facing copy was
 * written in release-note and implementation voice. This guards the vocabulary
 * so it cannot drift back in: the words below name the machinery, not the work.
 */
const IMPLEMENTATION_VOCABULARY: readonly RegExp[] = [
  /\badapters?\b/i,
  /\bbackend\b/i,
  /\bdurabl[ey]\b/i,
  /\bKB-scoped\b/i,
  /\bprimitives?\b/i,
  /\bGNN\b/,
  /\bhuman feedback loop\b/i,
  /\bschema-driven\b/i,
  /\bhot-swaps?\b/i,
  /\bre-renders?\b/i,
  /\bwired\b/i,
]

/** Release-note voice: describing what the software now does, not what you can do. */
const RELEASE_NOTE_VOICE: readonly RegExp[] = [
  /\bnow (?:reads|uses|supports|renders|includes)\b/i,
]

/**
 * Demo scaffolding leaking into analyst copy. Previously guarded by
 * `pages/__tests__/AnalystCopy.test.tsx` against a hand-maintained list of page
 * files; folded in here so new pages are covered without being remembered.
 */
const DEMO_SCAFFOLDING: readonly RegExp[] = [
  /seeded investigation graph/i,
  /seeded RAG service/i,
  /demo read model/i,
]

/**
 * One term per concept. RAG Chat showed "NO ACTIVE THREAD" and "NO ACTIVE
 * CONVERSATION" on the same screen next to a "New thread" button; the API, the
 * route and the stored records all say conversation, so that is the word.
 */
const REJECTED_SYNONYMS: readonly { term: RegExp; use: string }[] = [
  { term: /\bthreads?\b/i, use: 'conversation' },
]

describe('user-facing copy', () => {
  const copy = collectUserFacingCopy()

  it('scrapes prose from the app source', () => {
    // Guards the scraper itself: a broken scanner would silently pass every
    // vocabulary assertion below by finding nothing at all.
    expect(copy.length).toBeGreaterThan(100)
  })

  it('never names implementation machinery', () => {
    const violations = copy.filter((occurrence) =>
      IMPLEMENTATION_VOCABULARY.some((banned) => banned.test(occurrence.text)),
    )

    expect(violations.map((v) => `${v.file}: ${v.text}`)).toEqual([])
  })

  it('never describes the product in release-note voice', () => {
    const violations = copy.filter((occurrence) =>
      RELEASE_NOTE_VOICE.some((banned) => banned.test(occurrence.text)),
    )

    expect(violations.map((v) => `${v.file}: ${v.text}`)).toEqual([])
  })

  it('never dodges pluralization with "(s)"', () => {
    // `{n} document(s)` is a single word once trimmed, so the prose filter drops
    // it — but no identifier contains "(s)", so the raw candidates are safe here.
    const violations = collectCopyCandidates().filter((occurrence) =>
      /\w\(s\)/.test(occurrence.text),
    )

    expect(violations.map((v) => `${v.file}: ${v.text}`)).toEqual([])
  })

  it('uses one term per concept', () => {
    const violations = copy.flatMap((occurrence) =>
      REJECTED_SYNONYMS.filter((synonym) => synonym.term.test(occurrence.text)).map(
        (synonym) => `${occurrence.file}: ${occurrence.text} (say "${synonym.use}")`,
      ),
    )

    expect(violations).toEqual([])
  })

  it('never mentions demo or seed scaffolding', () => {
    const violations = copy.filter((occurrence) =>
      DEMO_SCAFFOLDING.some((banned) => banned.test(occurrence.text)),
    )

    expect(violations.map((v) => `${v.file}: ${v.text}`)).toEqual([])
  })
})

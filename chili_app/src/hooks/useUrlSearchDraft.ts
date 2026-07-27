import { useEffect, useRef, useState } from 'react'

/**
 * Keep a search box typeable while its value lives in the URL (UXA-401).
 *
 * A search input bound straight to a URL-derived value drops characters: the
 * router's state update is asynchronous, so a keystroke that lands before the
 * previous one has flushed re-renders the input with the older value and the
 * browser reverts what was typed. Typing "redwood" left `?q=wd`.
 *
 * The typed text is therefore local state, updated synchronously on every
 * keystroke, and the URL is written from it. When the URL changes for any other
 * reason — Clear filters, the back button, a shared link — the draft resyncs to
 * it; the ref is what distinguishes "the URL caught up with my typing" from
 * "the URL changed underneath me".
 *
 * `delayMs` debounces only the URL write, never the draft. Pass a delay when the
 * URL drives a server request (a keystroke per query is a query per keystroke);
 * leave it at 0 when filtering happens client-side and the write is free.
 */
export function useUrlSearchDraft(
  urlValue: string,
  commit: (next: string) => void,
  delayMs = 0,
): [string, (next: string) => void] {
  const [draft, setDraft] = useState(urlValue)
  const intended = useRef(urlValue)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Committing through a ref means a debounced write lands on the *latest*
  // commit — one that has seen any status toggled while the user was typing —
  // rather than the closure captured when the keystroke happened. Assigned in
  // an effect, never during render.
  const commitRef = useRef(commit)
  useEffect(() => {
    commitRef.current = commit
  })

  useEffect(() => {
    if (urlValue !== intended.current) {
      intended.current = urlValue
      setDraft(urlValue)
    }
  }, [urlValue])

  useEffect(() => () => {
    if (timer.current !== null) clearTimeout(timer.current)
  }, [])

  const change = (next: string) => {
    intended.current = next
    setDraft(next)
    if (timer.current !== null) clearTimeout(timer.current)
    if (delayMs <= 0) {
      commitRef.current(next)
      return
    }
    timer.current = setTimeout(() => {
      timer.current = null
      commitRef.current(next)
    }, delayMs)
  }

  return [draft, change]
}

/**
 * Small helpers for workspace state that must survive a reload.
 *
 * Selections like the active knowledge base and the active role decide what the
 * analyst can see. Holding them only in memory means a refresh, a bookmark, or a
 * shared link silently changes the workspace out from under them — so they are
 * persisted rather than re-derived from defaults on every mount.
 *
 * Storage can be unavailable (private mode, disabled cookies, non-browser test
 * environments). An unreadable or unwritable store is treated as "nothing
 * remembered" rather than an error: every caller has a defensible default, and
 * losing a preference is not worth failing a render over.
 */

export function readPersisted(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

export function writePersisted(key: string, value: string | null): void {
  try {
    if (value === null) {
      window.localStorage.removeItem(key)
      return
    }
    window.localStorage.setItem(key, value)
  } catch {
    // A failed write only costs the user this preference on the next reload.
  }
}

import '@testing-library/jest-dom/vitest'

// Tell React this is a valid `act()` environment so internal state updates
// during tests don't emit "not configured to support act" warnings.
declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true

// jsdom does not implement ResizeObserver. Provide a no-op so chart
// components that subscribe to size changes can render in tests.
if (typeof globalThis.ResizeObserver === 'undefined') {
  class ResizeObserverStub {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  globalThis.ResizeObserver = ResizeObserverStub as any
}

// Node 25 ships a built-in `localStorage` that lacks `.clear` and gets hoisted
// into vitest workers, shadowing jsdom's Storage on `window.localStorage`. Our
// tests rely on the standard Web Storage API, so we install an in-memory
// implementation on both `globalThis` and `window` before any suite runs.
class MemoryStorage implements Storage {
  private store = new Map<string, string>()

  get length(): number {
    return this.store.size
  }

  clear(): void {
    this.store.clear()
  }

  getItem(key: string): string | null {
    return this.store.get(key) ?? null
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null
  }

  removeItem(key: string): void {
    this.store.delete(key)
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value))
  }
}

const installStorage = (): void => {
  const localStorageInstance = new MemoryStorage()
  const sessionStorageInstance = new MemoryStorage()
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: localStorageInstance,
  })
  Object.defineProperty(globalThis, 'sessionStorage', {
    configurable: true,
    value: sessionStorageInstance,
  })
  if (typeof window !== 'undefined') {
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: localStorageInstance,
    })
    Object.defineProperty(window, 'sessionStorage', {
      configurable: true,
      value: sessionStorageInstance,
    })
  }
}
installStorage()


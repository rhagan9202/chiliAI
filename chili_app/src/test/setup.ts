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


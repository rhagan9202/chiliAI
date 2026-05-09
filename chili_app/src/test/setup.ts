import '@testing-library/jest-dom/vitest'

// Tell React this is a valid `act()` environment so internal state updates
// during tests don't emit "not configured to support act" warnings.
declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true


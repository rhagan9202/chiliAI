// Frontend types for the Config Editor API contracts.
// Mirrors the shape exposed by `backend/api/routers/config.py`.

import type { DomainConfig } from './domainConfig'

export interface ConfigValidationError {
  message: string
  path?: string
}

export interface SaveConfigResult {
  config: DomainConfig
}

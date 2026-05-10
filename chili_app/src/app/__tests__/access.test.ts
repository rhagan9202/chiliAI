import { describe, expect, it } from 'vitest'

import { getAllowedPageIds, getDefaultRole, getLandingRoute, isRouteAllowed } from '../access'
import type { DomainConfig, DomainFeatures } from '../../api/contracts'

const features: DomainFeatures = {
  capabilities: {
    rag_chat: true,
    risk_scoring: true,
    timeseries: true,
    gnn: true,
    explainability: true,
    ingestion: true,
  } as DomainFeatures['capabilities'],
  default_entity_type: 'provider',
  default_role: 'analyst',
  enabled_pages: ['dashboard', 'alerts', 'cases', 'investigation', 'configuration'],
  roles: {
    viewer: { landing_page: 'dashboard', pages: ['dashboard', 'alerts'], permissions: [] },
    analyst: {
      landing_page: 'alerts',
      pages: ['dashboard', 'alerts', 'cases', 'investigation'],
      permissions: ['acknowledge_alert'],
    },
    admin: {
      landing_page: 'configuration',
      pages: ['dashboard', 'alerts', 'cases', 'investigation', 'configuration'],
      permissions: ['acknowledge_alert', 'edit_config'],
    },
  },
}

const domainConfig = {
  ui: {
    navigation: {
      pages: [
        { id: 'dashboard', label: 'Dashboard', route: '/dashboard' },
        { id: 'alerts', label: 'Alerts', route: '/alerts' },
        { id: 'cases', label: 'Cases', route: '/cases' },
        { id: 'investigation', label: 'Investigation', route: '/investigation' },
        { id: 'configuration', label: 'Config', route: '/configuration' },
      ],
    },
  },
} as unknown as DomainConfig

describe('getDefaultRole', () => {
  it('returns null when features is undefined', () => {
    expect(getDefaultRole(undefined)).toBeNull()
  })

  it('returns features.default_role when set', () => {
    expect(getDefaultRole(features)).toBe('analyst')
  })

  it('falls back to first role key when default_role is missing', () => {
    const f = { ...features, default_role: null }
    expect(getDefaultRole(f)).toBe('viewer')
  })
})

describe('getAllowedPageIds', () => {
  it('returns [] when features is undefined', () => {
    expect(getAllowedPageIds(undefined, 'analyst')).toEqual([])
  })

  it('returns enabled_pages when no role selected', () => {
    expect(getAllowedPageIds(features, null).sort()).toEqual(
      ['alerts', 'cases', 'configuration', 'dashboard', 'investigation'],
    )
  })

  it('returns enabled_pages when selected role unknown', () => {
    expect(getAllowedPageIds(features, 'janitor').sort()).toEqual(
      ['alerts', 'cases', 'configuration', 'dashboard', 'investigation'],
    )
  })

  it('returns intersection of role.pages and enabled_pages for viewer', () => {
    expect(getAllowedPageIds(features, 'viewer').sort()).toEqual(['alerts', 'dashboard'])
  })

  it('returns intersection for analyst (no configuration)', () => {
    expect(getAllowedPageIds(features, 'analyst').sort()).toEqual(
      ['alerts', 'cases', 'dashboard', 'investigation'],
    )
  })

  it('returns intersection for admin (includes configuration)', () => {
    expect(getAllowedPageIds(features, 'admin').sort()).toEqual(
      ['alerts', 'cases', 'configuration', 'dashboard', 'investigation'],
    )
  })
})

describe('getLandingRoute', () => {
  it('returns /dashboard fallback when nothing is configured', () => {
    expect(getLandingRoute(undefined, undefined, null)).toBe('/dashboard')
  })

  it('honors role.landing_page when allowed', () => {
    expect(getLandingRoute(domainConfig, features, 'analyst')).toBe('/alerts')
  })

  it('falls back to default role landing when no selected role', () => {
    expect(getLandingRoute(domainConfig, features, null)).toBe('/alerts')
  })

  it('falls back to first allowed page when role landing not in allowed set', () => {
    const f = {
      ...features,
      roles: { ...features.roles, viewer: { ...features.roles.viewer, landing_page: 'cases' } },
    }
    // viewer pages = [dashboard, alerts]; cases not allowed → first allowed = dashboard
    expect(getLandingRoute(domainConfig, f, 'viewer')).toBe('/dashboard')
  })
})

describe('isRouteAllowed', () => {
  it('returns true when features is undefined', () => {
    expect(isRouteAllowed(domainConfig, undefined, 'viewer', '/configuration')).toBe(true)
  })

  it('blocks viewer from configuration', () => {
    expect(isRouteAllowed(domainConfig, features, 'viewer', '/configuration')).toBe(false)
  })

  it('allows analyst on cases', () => {
    expect(isRouteAllowed(domainConfig, features, 'analyst', '/cases')).toBe(true)
  })

  it('allows admin on configuration', () => {
    expect(isRouteAllowed(domainConfig, features, 'admin', '/configuration')).toBe(true)
  })

  it('matches sub-paths under a configured route', () => {
    expect(isRouteAllowed(domainConfig, features, 'analyst', '/investigation/provider-1')).toBe(true)
  })

  it('returns true for paths not matched by any configured page (no opinion)', () => {
    expect(isRouteAllowed(domainConfig, features, 'viewer', '/auth/callback')).toBe(true)
  })
})

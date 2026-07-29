import { describe, expect, it } from 'vitest'

import {
  getAllowedPageIds,
  getDefaultRole,
  getLandingRoute,
  getRouteBlockReason,
  isRouteAllowed,
} from '../access'
import type { DomainConfig, DomainFeatures } from '../../api/contracts'

const features: DomainFeatures = {
  capabilities: {
    rag_chat: true,
    risk_scoring: true,
    timeseries: true,
    gnn: true,
    explainability: true,
    structured_ingestion: true,
    peer_stats: false,
  },
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

  it('acts as the default role when no role is selected', () => {
    // No explicit selection means the workspace is acting as `default_role`
    // (analyst), so it must get analyst's pages — not every enabled page.
    expect(getAllowedPageIds(features, null).sort()).toEqual(
      ['alerts', 'cases', 'dashboard', 'investigation'],
    )
  })

  it('falls back to the default role when the selected role is not in this pack', () => {
    // A role remembered from a different pack must never out-grant a real role
    // here. Failing open to every enabled page handed an unrecognised role the
    // configuration page that the default analyst role is denied.
    expect(getAllowedPageIds(features, 'janitor').sort()).toEqual(
      ['alerts', 'cases', 'dashboard', 'investigation'],
    )
    expect(getAllowedPageIds(features, 'janitor')).not.toContain('configuration')
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

  it('blocks a page the SPA implements but the active pack does not declare', () => {
    // /housing is a real page in this SPA, but this pack's navigation has no
    // housing entry — rendering Air Force content under a Medicare pack is a
    // cross-domain leak, not a "no opinion" case (UXA-103).
    expect(isRouteAllowed(domainConfig, features, 'analyst', '/housing')).toBe(false)
  })

  it('blocks an undeclared page for every role, not just restricted ones', () => {
    expect(isRouteAllowed(domainConfig, features, 'admin', '/housing')).toBe(false)
  })

  it('allows a page the active pack does declare', () => {
    // The same gate must not break the pack that owns the page: under the
    // housing pack, /housing is declared and granted, so it renders.
    const housingConfig = {
      ui: {
        navigation: {
          pages: [{ id: 'housing', label: 'Housing', route: '/housing' }],
        },
      },
    } as unknown as DomainConfig
    const housingFeatures = {
      capabilities: {},
      default_role: 'executive',
      enabled_pages: ['housing'],
      roles: { executive: { landing_page: 'housing', pages: ['housing'], permissions: [] } },
    } as unknown as DomainFeatures

    expect(isRouteAllowed(housingConfig, housingFeatures, 'executive', '/housing')).toBe(true)
  })

  it('allows detail routes that hang off a page rather than being nav pages', () => {
    // Scorecard runs are reached from the housing dashboard and never appear in
    // navigation, so they must not be gated as if they were a pack page.
    expect(isRouteAllowed(domainConfig, features, 'analyst', '/scorecards/run-1')).toBe(true)
  })

  it('refuses a restricted page to a role this pack does not define', () => {
    // The stale-role path: a role carried over from another pack collapsed
    // gating to pack level, so /configuration opened for a role that does not
    // exist while the real analyst role is refused it.
    expect(isRouteAllowed(domainConfig, features, 'janitor', '/configuration')).toBe(false)
    expect(getRouteBlockReason(domainConfig, features, 'janitor', '/configuration')).toBe('role')
  })
})

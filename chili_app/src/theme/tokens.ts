export const colors = {
  bg: '#05080f',
  s1: '#080d1a',
  s2: '#0c1222',
  s3: '#101828',
  b0: '#182033',
  b1: '#1e2c44',
  b2: '#253450',
  cyan: '#00d4ff',
  amber: '#f59e0b',
  red: '#ff4040',
  green: '#00e676',
  purple: '#a855f7',
  text: '#e2eaf6',
  dim: '#8899bb',
  muted: '#3d5070',
} as const

export const typography = {
  display: "'Oxanium', sans-serif",
  body: "'IBM Plex Sans', system-ui, sans-serif",
  mono: "'IBM Plex Mono', ui-monospace, monospace",
} as const

export const spacing = {
  xs: '4px',
  sm: '8px',
  md: '12px',
  lg: '16px',
  xl: '22px',
  xxl: '24px',
} as const

export const radii = {
  sm: '6px',
  md: '9px',
  lg: '12px',
  pill: '999px',
} as const

export const semanticColors = {
  primary: colors.cyan,
  highRisk: colors.red,
  mediumRisk: colors.amber,
  policyKnowledgeGraph: colors.green,
  networkSignal: colors.purple,
} as const
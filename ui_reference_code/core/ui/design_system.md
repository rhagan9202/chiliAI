# Design System
**IntegrityAI · Program Integrity Accelerator**
`domain-pack/docs/design_system.md`

---

## Aesthetic Philosophy

The visual language of IntegrityAI is **"dark intelligence"** — the aesthetic of a purpose-built analytical instrument, not a consumer dashboard. Every visual decision is calibrated for two simultaneous goals:

1. **Operational usability** — analysts can work in this environment for hours without fatigue. Density is controlled. Hierarchy is immediate. Color means something specific every time it appears.
2. **Stakeholder persuasion** — in a demo, the UI must signal sophistication in the first 3 seconds. Government staff seeing their first AI-native tool need to feel that this is categorically different from what they use today.

The aesthetic deliberately avoids:
- White or light backgrounds (too much contrast fatigue for data-dense work)
- Purple gradients on white (the most common "AI product" cliché)
- Generic sans-serif body fonts like Inter, Roboto, or Arial
- Flat, icon-heavy sidebars that read as generic SaaS
- Cards with heavy drop shadows (too much visual noise in a data-dense UI)

---

## Color System

### Token Definitions

All colors are defined in a single shared token object `const C = { ... }` in the source. Every color reference in the UI uses a `C.tokenName` reference — never a hardcoded hex value.

```
const C = {
  // Backgrounds (darkest → lightest)
  bg:     '#05080f',   // True app background — deepest layer
  s1:     '#080d1a',   // Sidebar, panels, overlays — second layer
  s2:     '#0c1222',   // Card surfaces — primary content layer
  s3:     '#101828',   // Inset areas, expanded rows, tab content

  // Borders (subtle → visible)
  b0:     '#182033',   // Default card border — barely visible
  b1:     '#1e2c44',   // Slightly elevated border — hover states
  b2:     '#253450',   // Active/selected border — visible separation

  // Semantic colors
  cyan:   '#00d4ff',   // Medicare accent / primary program color
  amber:  '#f59e0b',   // Warning / medium risk / at-risk amounts
  red:    '#ff4040',   // High risk / violations / critical alerts
  green:  '#00e676',   // PKG / AI intelligence layer ONLY
  purple: '#a855f7',   // Medicaid accent / network co-billing signal

  // Text
  text:   '#e2eaf6',   // Primary text — slightly cool white
  dim:    '#8899bb',   // Secondary text — muted blue-grey
  muted:  '#3d5070',   // Tertiary text — very subdued, metadata only
}
```

---

### Color Roles and Usage Rules

#### Background Layers
The four background values form a strict depth hierarchy. Lower layer values are never used on top of higher ones.

| Token | Hex | Role | Used For |
|-------|-----|------|----------|
| `bg` | `#05080f` | Ground | Page background — never as a surface |
| `s1` | `#080d1a` | Shell layer | Sidebar, top bar, AI panel, modal backdrops |
| `s2` | `#0c1222` | Card layer | Primary content cards, chart containers |
| `s3` | `#101828` | Inset layer | Expanded rows, tab content areas, nested cards |

**Rule:** Cards always sit on `bg` or `s1`. Nested content within a card uses `s3`. Never use `bg` as a card background.

---

#### Semantic Color Rules

**Red (`#ff4040`) — High Risk / Violation**
- Risk score ≥90 badge
- "LIKELY VIOLATION" determination badge
- Critical policy gap severity
- HCPCS consolidation signal accent
- Provider icon background when risk is high
- Never use for decorative purposes

**Amber (`#f59e0b`) — Medium Risk / Caution / Money**
- Risk score 75–89 badge
- "POSSIBLE VIOLATION" determination badge
- At-risk dollar amounts (`signal.atRisk`, `case.atRisk`)
- Medium priority compliance actions
- Policy gap: HIGH severity
- "Unassigned" analyst label
- E&M upcoding signal accent

**Cyan (`#00d4ff`) — Medicare / Primary Program / Information**
- Medicare FFS program accent (all program-context UI)
- Low risk badge (below 75)
- AI panel active state
- "Review" button accent
- Sidebar active nav item
- `ConfBar` default fill color
- Never use for warnings or violations

**Purple (`#a855f7`) — Medicaid / Network Signal**
- Medicaid FFS program accent (all program-context UI when Medicaid active)
- Network co-billing signal accent (Signal 3 in Provider Deep-Dive)
- Replaces cyan in all program-accent roles when Medicaid is selected

**Green (`#00e676`) — PKG Intelligence Layer ONLY**
- Policy Knowledge Graph branding and badges
- Policy citation source labels
- Relevance score rings
- PKG tab badge, PKG nav badge
- "Add to Policy Brief" button
- Policy Intelligence screen accent
- Policy gap recommendation callouts
- **Critical rule:** Green is reserved exclusively for the PKG/AI intelligence layer. It must never appear as a risk indicator, status color, or trend indicator. Its exclusivity is what makes it legible as "retrieved knowledge."

---

#### Border Usage

Borders are used to separate surfaces, not to add decoration. They are always 1px and semi-transparent.

| Token | Hex | Use |
|-------|-----|-----|
| `b0` | `#182033` | Default card border — always present on cards |
| `b1` | `#1e2c44` | Hover state border, elevated panels |
| `b2` | `#253450` | Active/expanded card border, selected state |

**Pattern for tinted borders:** When a card is semantically colored (e.g., a red-tinted signal panel), use `${C.red}30` (30 = 19% opacity hex) as the border color. Never use a full-opacity semantic color as a border.

---

#### Opacity Conventions for Color Tinting

Tinted backgrounds and borders follow a strict opacity convention:

| Use | Opacity Suffix | Example |
|-----|---------------|---------|
| Background tint (light) | `08`–`10` | `${C.red}08` = barely visible red tint |
| Background tint (visible) | `12`–`18` | `${C.cyan}15` = soft cyan background |
| Border (subtle) | `20`–`30` | `${C.green}20` = very subtle green border |
| Border (visible) | `35`–`50` | `${C.red}35` = visible red border |
| Glow / shadow | `40`–`80` | `${C.cyan}40` = medium cyan glow |
| Icon background fill | `15`–`20` | `${C.amber}15` = amber icon box background |

---

### Program Color Theming

When the program switcher toggles, `pd.color` (the active program color) replaces all generic accent references. Components that use `pd.color` (or `ac` as a local alias) automatically reaccent.

| Context | Medicare Value | Medicaid Value |
|---------|---------------|----------------|
| Sidebar active nav border | `C.cyan` | `C.purple` |
| Active tab underline | `C.cyan` | `C.purple` |
| Program badge | `C.cyan` | `C.purple` |
| Logo shield gradient | `C.cyan` | `C.purple` |
| KPI card accent line | `C.cyan` | `C.purple` |
| Program switcher active button | `C.cyan` fill | `C.purple` fill |

---

## Typography

### Font Stack

```css
@import url('https://fonts.googleapis.com/css2?family=Oxanium:wght@400;500;600;700;800&family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
```

### Font Roles

| Font | Variable | Role | Never Use For |
|------|----------|------|---------------|
| Oxanium | `oxan` | Display, scores, KPI values, section headers, tab labels, risk scores | Long body copy, policy snippet text |
| IBM Plex Sans | (body default) | All body text, descriptions, card content, paragraph copy | Data codes, IDs, numeric scores |
| IBM Plex Mono | `mono` | HCPCS codes, NPI numbers, case IDs, column headers, metadata labels, percentage values in data contexts | Prose sentences |

### Type Scale

| Use | Font | Size | Weight | Color |
|-----|------|------|--------|-------|
| Screen title | Oxanium | 18px | 700 | `C.text` |
| Card section header | Oxanium | 14px | 700 | `C.text` |
| Signal panel header | Oxanium | 13px | 700 | `C.text` |
| Provider name (header) | Oxanium | 21px | 800 | `C.text` |
| Risk score (large) | Oxanium | 54px | 800 | `C.red` |
| KPI value | Oxanium | 26px | 800 | `C.text` |
| Stat card value (large) | Oxanium | 20–24px | 800 | semantic color |
| Stat card value (small) | Oxanium | 18px | 800 | semantic color |
| Tab label | Oxanium | 12px | 700 | active: `ac`, inactive: `C.muted` |
| Body paragraph | IBM Plex Sans | 12–13px | 400 | `C.dim` |
| Provider name (row) | IBM Plex Sans | 14px | 500 | `C.text` |
| Secondary label | IBM Plex Sans | 12px | 400 | `C.dim` |
| Metadata / sub-label | IBM Plex Sans | 11–12px | 400 | `C.muted` |
| Column headers | IBM Plex Mono | 9–10px | 400 | `C.muted` · letter-spacing: 0.06–0.08em |
| NPI / Case ID | IBM Plex Mono | 10–11px | 400 | `C.muted` or `C.cyan` |
| Code labels (HCPCS) | IBM Plex Mono | 10px | 400 | `C.text` |
| Data chip labels | IBM Plex Mono | 9–10px | 400 | semantic color |
| Percentage in data | IBM Plex Mono | 10px | 500 | `C.dim` |

### Letter Spacing

Monospace column headers and badge labels use elevated letter spacing to improve legibility at small sizes:

| Context | Letter Spacing |
|---------|---------------|
| Column header labels (`PROVIDER`, `RISK SCORE`) | `0.06–0.08em` |
| Chip/badge labels (`HIGH RISK`, `PKG`) | `0.04–0.07em` |
| Section sub-labels (`AI ANALYSIS ·`) | `0.06–0.07em` |
| Normal body text | `0` (default) |

### Line Height

| Context | Line Height |
|---------|------------|
| Policy snippet / reasoning paragraphs | `1.65–1.75` |
| Standard body descriptions | `1.5–1.6` |
| Tight metadata / chip labels | `1.0–1.2` |
| KPI values / scores | `1.0` (explicit) |

---

## Spacing System

IntegrityAI uses a pragmatic spacing system rather than a strict grid. The following values are used consistently:

| Scale | px | Use |
|-------|----|-----|
| xs | 4px | Icon-to-label gap, tight chip padding |
| sm | 7–8px | Chip padding (h), icon box padding, tight row gaps |
| md | 10–12px | Standard card internal padding (compact), stat card padding |
| lg | 14–16px | Row padding, card-to-card gaps, section gaps |
| xl | 18–22px | Card padding, chart container padding |
| xxl | 24px | Screen outer padding (all main content areas) |

### Card Anatomy

Every card shares this structural pattern:

```
border-radius: 10–12px
border: 1px solid C.b0
background: C.s2
padding: 20–22px (standard)  |  13–16px (compact/row)
overflow: hidden
```

Optional top accent line (used on KPI cards and colored signal panels):
```
position: absolute, top: 0, left: 0, right: 0, height: 2px
background: linear-gradient(90deg, transparent, {color}80, transparent)
```

### Border Radius

| Element | Radius |
|---------|--------|
| Main content cards | 12px |
| Compact row cards / nested cards | 9–10px |
| Buttons | 6–8px |
| Chips / badges | 4–5px |
| Relevance score rings | N/A (SVG circle) |
| Progress bars | 2px |
| Icon boxes | 6–9px |
| User avatar | 50% (circle) |

---

## Iconography

**Library:** Lucide React (`lucide-react@0.263.1`)

### Icon Sizing Convention

| Context | Size |
|---------|------|
| Sidebar nav items | 15px |
| Section header icons | 17–18px |
| Card header icons (in icon box) | 13–15px |
| Inline / body icons | 11–14px |
| Provider header icon | 24px |
| Top bar icons (bell, search) | 13–14px |

### Icon Box Pattern

Icons in card headers are always wrapped in a tinted box:

```
width: 24–34px  (varies by context)
height: same as width
border-radius: 6–10px
background: ${color}15  (15% opacity tint)
display: flex, align-items: center, justify-content: center
```

---

## Elevation and Depth

IntegrityAI does not use traditional box shadows for elevation. Depth is communicated through:

1. **Background layer progression** (`bg` → `s1` → `s2` → `s3`)
2. **Border visibility** (`b0` default → `b1` hover → `b2` active)
3. **Top accent lines** on KPI cards (1–2px gradient line)
4. **Semantic glow effects** on risk dots: `box-shadow: 0 0 6px {color}`

**Rule:** Never add `box-shadow` to cards. It creates visual noise in a data-dense dark theme.

---

## Animation and Motion

### Defined Keyframes

```css
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes slideRight {
  from { opacity: 0; transform: translateX(24px); }
  to   { opacity: 1; transform: translateX(0); }
}

@keyframes pulseRing {
  0%, 100% { box-shadow: 0 0 0 0 rgba(0,212,255,0.4); }
  50%       { box-shadow: 0 0 0 6px rgba(0,212,255,0); }
}

@keyframes pkgPulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.55; }
}
```

### Animation Usage

| Class / Element | Animation | Duration | Easing | Trigger |
|-----------------|-----------|----------|--------|---------|
| `.fu` (screen content) | `fadeUp` | 0.35s | `ease` | Mount |
| `.sr` (AI panel) | `slideRight` | 0.4s | `cubic-bezier(.16,1,.3,1)` | Panel open |
| Feed rows | `fadeUp` with staggered `animation-delay: {i*0.04}s` | 0.35s | `ease` | Mount |
| AI panel active dot | `pulseRing` | 2s | `ease-in-out` | While panel open |
| PKG badge | `pkgPulse` | 2.5s | `ease-in-out` | Continuous |
| AI panel slide | `margin-right` transition | 0.35s | `cubic-bezier(.16,1,.3,1)` | Panel toggle |
| Tab underline | color / border transition | 0.15s | `default` | Tab change |
| Row hover background | background transition | 0.15s | `default` | Hover |
| Button states | all properties | 0.15s | `default` | Interaction |

### Motion Principles

- **Fade + translate is the default enter.** Never use scale animations — they feel consumer, not enterprise.
- **Stagger feed rows** — each row enters 40ms after the previous one, creating a cascade that draws the eye down the list
- **AI panel uses spring easing** — `cubic-bezier(.16,1,.3,1)` gives a subtle deceleration that feels responsive without bouncing
- **Continuous animations are used sparingly** — only the AI active dot (pulseRing) and PKG badge (pkgPulse). Everything else animates on interaction or mount only.

---

## Data Visualization Style

### Chart Library
Recharts. All charts use `<ResponsiveContainer>` for fluid width.

### Chart Color Assignments

| Data Series | Color | Notes |
|-------------|-------|-------|
| Primary program series | `program.color` (cyan/purple) | Area charts, trend lines |
| Recovery / savings | `C.green` | Always green — money recovered |
| Provider value (vs. peers) | `C.red` | The subject is always the "alarming" series |
| 90th percentile peer | `C.amber` | Middle reference |
| Peer median | `C.cyan` (low opacity) | Background reference |
| Secondary signal | `C.amber` | Billing timeline, secondary trends |

### Chart Axis Style

```
axisLine: false
tickLine: false
tick: { fill: C.muted, fontSize: 9–10, fontFamily: 'IBM Plex Mono' }
```

### Chart Grid Style

```
<CartesianGrid strokeDasharray="3 3" stroke={C.b0} />
```

### Tooltip Style

```javascript
const tipStyle = {
  contentStyle: {
    background: C.s3,
    border: `1px solid ${C.b2}`,
    borderRadius: 8,
    fontSize: 11
  },
  labelStyle: { color: C.text }
}
```

### Area Chart Gradient Pattern

All area fills use a top-to-bottom opacity gradient from ~35–40% to ~2%:

```jsx
<defs>
  <linearGradient id="gX" x1="0" y1="0" x2="0" y2="1">
    <stop offset="5%"  stopColor={color} stopOpacity={0.35}/>
    <stop offset="95%" stopColor={color} stopOpacity={0.02}/>
  </linearGradient>
</defs>
```

### Chart Margins

```javascript
margin={{ top: 5, right: 10–20, bottom: 0–5, left: -15 to -18 }}
```
The negative left margin compensates for Recharts' default Y-axis label padding.

### SVG Custom Charts (Network Diagram, Gap Matrix)

For charts requiring custom layouts not supported by Recharts (network node-edge diagrams, bubble scatter plots), raw SVG is used with a `viewBox` and `width="100%"` for fluid scaling.

SVG text elements use:
```
fontFamily: 'IBM Plex Mono' (for data labels)
fontFamily: 'IBM Plex Sans' (for node names)
fill: C.text / C.dim / C.muted (by hierarchy)
```

---

## Component Visual Patterns

### Chip / Badge

```
padding: 2px 8px
border-radius: 4px
border: 1px solid ${color}30
background: ${color}10
font: IBM Plex Mono, 9–10px
color: {semantic color}
letter-spacing: 0.04–0.07em
white-space: nowrap
```

### Progress Bar (ConfBar)

```
container: height 3px, background C.b0, border-radius 2px, overflow hidden
fill: width {val}%, height 100%, background {color}, border-radius 2px
label: IBM Plex Mono 10px, C.dim, min-width 28px
```

### Risk Dot

```
width: 7px, height: 7px
border-radius: 50%
background: {semantic color}
box-shadow: 0 0 6px {semantic color}
```

### Relevance Score Ring (SVG)

```
viewBox: 36×36
outer track circle: r=14, stroke C.b0, stroke-width 3
fill arc: r=14, stroke C.green, stroke-width 3
  stroke-dasharray: {score * 0.879} 87.9   (87.9 = circumference of r=14)
  stroke-linecap: round
  transform: rotate(-90deg)  (starts arc at top)
center label: IBM Plex Mono 9px, C.green, font-weight 600
```

### Step Chain Visual (Policy reasoning)

```
Each step: padding 3px 8px, border-radius 4px,
  background: ${detColor}15, border: 1px solid ${detColor}30,
  font: IBM Plex Mono 9px, color: detColor
Separator: ArrowRight icon 9px, color C.muted
```

---

## Scrollbar Style

```css
::-webkit-scrollbar        { width: 4px; height: 4px; }
::-webkit-scrollbar-track  { background: transparent; }
::-webkit-scrollbar-thumb  { background: C.b1; border-radius: 4px; }
```

Scrollbars are intentionally minimal — 4px, no track — to preserve the clean dark surface without visual noise from scrollable containers.

---

## Layout Structure

```
viewport
├── Sidebar (220px fixed, full height)
│   ├── Logo block
│   ├── Program switcher
│   ├── Nav items (flex:1, scrollable if needed)
│   └── AI toggle (bottom, pinned)
└── Main area (flex:1, column)
    ├── Top bar (54px fixed height)
    └── Content area (flex:1, overflow-y: auto)
        └── [Active screen content, padding: 24px]

AI Panel overlay (420px, fixed right, full height, z-index: 100)
  └── Activated by AI toggle, pushes main area via margin-right
```

**Critical layout rule:** The AI panel uses `position: fixed` and pushes content via `margin-right: 420px` transition on the main area — it does not use a CSS overlay that covers content. This ensures all screen content remains visible (just narrower) when the AI panel is open.

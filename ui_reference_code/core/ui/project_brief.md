# Project Brief
**IntegrityAI · Program Integrity Accelerator**
`domain-pack/docs/project_brief.md`

---

## What This Is

**IntegrityAI** is an AI-powered anomaly detection and program integrity platform purpose-built for CMS (Centers for Medicare & Medicaid Services) program integrity staff. It surfaces fraudulent, wasteful, and abusive billing patterns in Medicare Fee-for-Service and Medicaid Fee-for-Service claims data, grounds those findings in CMS policy, and produces auditable compliance actions — all within a single investigative workflow.

The product is currently at **demo / prototype stage**, designed to win stakeholder buy-in from government program integrity leadership. The UI must function as both a working tool demo and a persuasive narrative device in a single sitting.

---

## The Problem Being Solved

Traditional program integrity tools are **rule-based and reactive**: they fire alerts when a claim crosses a hard-coded threshold, but provide no explanation, no policy grounding, and no investigative workflow. Analysts receive a list of flagged providers with no context for why, no comparison to peers, and no guidance on what to do next.

The result is three compounding failures:

1. **Low analyst throughput** — investigators spend most of their time figuring out *whether* something is wrong before they can act on it
2. **Inconsistent enforcement** — different analysts reach different conclusions on identical patterns because there is no shared policy grounding
3. **No systemic learning** — individual case findings never surface as program-level policy insights for CMS leadership

IntegrityAI solves all three by making the AI's reasoning visible, grounded, and actionable at every level of the organization.

---

## The Differentiating Capability: Policy Knowledge Graph (PKG)

The single most important technical and product differentiator is the **Policy Knowledge Graph**. Most AI fraud detection tools stop at anomaly scoring. IntegrityAI goes further:

1. Each flagged anomaly signal is used to **query the PKG** — a structured index of CMS coding guidance, billing rules, federal statutes (AKS, Stark Law), OIG work plan priorities, and NCCI edits
2. The most relevant policy sections are **retrieved and ranked** by relevance to the specific signal
3. The AI uses those retrieved sections as **grounding evidence** to determine: (a) is this a likely violation or a legitimate corner case?, (b) what compliance actions should follow?, and (c) does this case reveal a gap or ambiguity in CMS's own policies?

This means every finding in IntegrityAI is **auditable, citation-backed, and defensible** — which is non-negotiable for government enforcement contexts.

The PKG also powers a fourth output type targeted at CMS leadership: **systemic policy gap identification** — patterns of cases where the AI consistently finds that existing policy is ambiguous or lacks quantitative enforcement thresholds.

---

## Users and Their Jobs

### User 1 — Program Integrity Analyst (Fraud Investigator)
**Primary user. Daily active.**

- Triages the anomaly detection feed to prioritize which providers to investigate
- Reviews provider evidence dossiers (billing patterns, peer comparisons, network maps)
- Reads AI-generated policy determinations to decide whether to open a case
- Logs cases, notes, and compliance actions to the case management system
- Asks the AI Investigator panel questions during active investigation

**Design implication:** The analyst's screen is the Provider Deep-Dive. Everything on this screen must help them make a defensible decision faster. They are skeptical of AI — they need to see the evidence and the reasoning, not just a score.

---

### User 2 — Supervisory Analyst / Queue Manager
**Daily active. Often the demo audience.**

- Monitors program-level KPIs and queue health on the Dashboard
- Assigns cases to analysts, manages workload distribution
- Escalates high-risk cases
- Reviews the analyst's policy determinations before formal action

**Design implication:** The supervisor sees the Dashboard first. It must communicate health status, trends, and urgency at a glance. The queue health panel must make workload imbalances immediately visible.

---

### User 3 — CMS Program Leadership
**Weekly. High-stakes audience. Often the economic buyer.**

- Reviews systemic policy gaps and oversight weaknesses
- Approves policy change recommendations for escalation to CMS rulemaking
- Wants program-level ROI evidence (savings recovered, fraud deterred)
- Does not need to see individual provider cases

**Design implication:** The Policy Intelligence screen is built exclusively for this persona. It must feel authoritative, not operational. Data must be aggregated and framed in terms of policy impact and dollar exposure — not individual claim details.

---

## Key Design Decisions and Rationale

### Decision 1 — Dark, High-Contrast Visual Theme
**Choice:** Deep navy/near-black background (`#05080f`) with colored accent layers.

**Rationale:** Program integrity analysts work long hours staring at data-dense screens. Dark themes reduce eye strain in sustained use. More importantly, the dark background creates a "mission control" aesthetic that signals sophistication and seriousness to government stakeholders — it reads as a purpose-built intelligence tool, not a repackaged BI dashboard. This contrast with the legacy tools (often white-background Excel or Cognos reports) is intentional and memorable in a demo.

---

### Decision 2 — Oxanium for Display Type, IBM Plex Sans for Body, IBM Plex Mono for Data
**Choice:** Three-font system with a clear hierarchy.

**Rationale:**
- **Oxanium** (display/headlines/scores) — geometric, technical, slightly futuristic. Signals that this is an AI-native product, not a legacy tool wearing a new skin. Used for risk scores, KPI values, and section headers.
- **IBM Plex Sans** (body copy, labels) — humanist, readable, designed for long-form data display. The IBM provenance carries a subtle "enterprise-grade" authority in government contexts.
- **IBM Plex Mono** (codes, IDs, metadata) — instantly signals "this is a data field, not prose." Used for NPIs, HCPCS codes, case IDs, and field labels. Makes clinical/regulatory codes feel precise and auditable.

The three-font system creates an immediate visual hierarchy: what is a score, what is text, what is a code identifier. This reduces cognitive load for analysts processing high volumes of structured data.

---

### Decision 3 — Three-Color Severity System (Red / Amber / Cyan) + Program Colors
**Choice:** Red = high risk / violation, Amber = medium risk / caution, Cyan = Medicare accent, Purple = Medicaid accent, Green = PKG / AI intelligence layer.

**Rationale:**
- Red/amber/green is a universal traffic-light convention, but green in a fraud detection tool reads as "safe" — which is misleading. **Cyan** replaces green as the primary program accent, reserving green exclusively for the PKG and AI intelligence layer. This creates a visual language: anything green is the AI's knowledge, not a risk indicator.
- **Purple** for Medicaid creates immediate program disambiguation — when the program switcher toggles, the entire UI reaccents, making it impossible to confuse which program you are viewing.
- The PKG green (`#00e676`) is a distinct, vivid green specifically to make the "intelligence layer" feel like a different kind of information — retrieved knowledge, not computed score.

---

### Decision 4 — AI Embedded Throughout, Not Siloed
**Choice:** AI reasoning appears inline in the feed, in signal panels, in policy citation cards, and in a persistent side panel — not in a separate "AI" section.

**Rationale:** Government PI staff are deeply skeptical of "black box" AI. If the AI is in its own tab or section, it reads as optional and untrustworthy. By embedding AI reasoning at every step — the inline reason code on a feed row, the reasoning chain on a policy card, the determination badge on a signal — the AI becomes part of the investigative workflow rather than a separate system the analyst is asked to trust. The analyst never has to go to the AI; the AI is already where they are.

---

### Decision 5 — Policy Analysis as a Distinct Tab with "PKG" Badging
**Choice:** Policy Analysis is the second tab in Provider Deep-Dive, prominently badged with a green "PKG" pill.

**Rationale:** The PKG is the product's primary differentiator. It must be unmissable in a demo. Placing it as a tab rather than a separate screen keeps it in context — an analyst reviewing a provider's billing patterns can immediately pivot to the policy grounding without losing their place. The "PKG" badge makes it visually distinct from the other tabs and gives stakeholders a concrete label to attach to the capability.

---

### Decision 6 — Policy Intelligence as a Separate Screen for CMS Leadership
**Choice:** A dedicated fifth screen in the nav, role-gated for CMS leaders.

**Rationale:** The three output types of the PKG serve different audiences at different timescales:
- Violation determination + compliance actions → **analyst**, immediate, case-level
- Policy gap identification → **CMS leadership**, strategic, program-level

Mixing these on the same screen would compromise both. The Policy Intelligence screen gives leadership a view they own — framed in terms of dollar exposure and policy recommendations, not individual NPIs and claim codes.

---

### Decision 7 — Program Switcher in the Sidebar, Not the Top Bar
**Choice:** Medicare/Medicaid toggle is in the sidebar, not the global top navigation.

**Rationale:** The program context is a **workspace-level setting**, not a page-level filter. Putting it in the sidebar treats it as a global context switch — the whole UI reaccents and all data updates. Putting it in the top bar would imply it's a filter within a shared dataset. The distinction matters for multi-program deployments where a supervisor might be responsible for one program only, and for ensuring analysts never accidentally view the wrong program's data.

---

## What This Is Not

- **Not a claims adjudication system** — IntegrityAI does not make payment decisions
- **Not a case management system of record** — the case management screen is a lightweight tracker; formal case files live in the agency's system of record (e.g., CMS's existing case management infrastructure)
- **Not a real-time system** — anomaly detection runs on claims data at a configured cadence (daily/weekly batch), not on streaming claims
- **Not a replacement for human judgment** — all AI determinations are advisory. Analysts make the final call. The UI must never imply otherwise.

---

## Technical Context

- **Frontend:** React (single JSX file for the demo). Production would componentize into a proper file structure.
- **Charts:** Recharts library for all data visualizations
- **Icons:** Lucide React icon library
- **Fonts:** Google Fonts (Oxanium, IBM Plex Sans, IBM Plex Mono) loaded via `@import`
- **Styling:** Inline styles with a shared design token object (`const C = { ... }`). No external CSS framework.
- **AI Panel:** Simulated in the demo with canned responses. Production connects to an LLM API with a structured system prompt injecting provider context and retrieved PKG citations.
- **PKG:** Simulated in the demo with static mock data. Production queries a vector-indexed policy document store.

---

## Demo Narrative Arc

The intended demo flow for a government stakeholder presentation:

1. **Dashboard** — "Here's the program at a glance. $52.7M in potential recovery. The AI flagged 3,241 providers this quarter."
2. **Anomaly Feed** — "Here's how analysts triage. Every alert has a risk score, a confidence level, and an AI reason code — no more black boxes."
3. **Provider Deep-Dive → Overview** — "Let's look at Advanced Pain Specialists. Three signals: HCPCS consolidation, E&M upcoding, network co-billing. Here's the evidence for each."
4. **Provider Deep-Dive → Policy Analysis** — "Now here's what makes us different. The AI queried our Policy Knowledge Graph and retrieved the exact CMS policy sections relevant to each signal. It determined: likely violation, 91% confidence. Here are the recommended actions, grounded in IOM §30.6.1."
5. **Policy Intelligence** — "And here's the view for your leadership team. Across all cases this quarter, the AI identified 14 policy gaps — places where CMS's own rules lack clear enforcement thresholds. Here are our recommended policy changes."

Each screen transition should feel like a zoom-out: from individual claim → provider dossier → policy grounding → systemic insight.

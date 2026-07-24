# chiliAI — CMS Fraud Presenter Script

**Audience:** Program integrity leadership, technical evaluators
**Run time:** ≤ 10 minutes (≈ 8:15 without the optional Act 3 live pack switch)
**Demo environment:** Live UI at `localhost:5173` against a running `make dev` stack, brought up with `make demo-cms`
**Domain pack:** `medicare_fraud_cms_desynpuf` ("Medicare Fraud Detection (CMS DE-SynPUF)")
**Data:** the 1% Tennessee subset (see Key Numbers below) — every number in this script is either sourced from `sample_data/CMS/tn_subset/MANIFEST.json` or explicitly called out as "live on screen" because it depends on the run.
**Version:** BL-051 / Sprint 2026-28 D1, 2026-07-23

> **Truth discipline:** every claim in this script was checked against the running component code before being written down. If a screen changes, the claim must change with it — do not "sell" a capability this document doesn't name.

---

## Before You Start

**Setup checklist (5 min before the room fills):**
- [ ] Stack is up: `make dev` (or already running), then `make demo-cms` has completed — it prints a KB id and the exact walkthrough URLs at the end. Use those URLs; do not guess at routes.
- [ ] Know this if asked: `make demo-cms` explicitly triggers the analytics-review pass (GNN/risk/explainability → alerts) for the KB's top-3 highest-risk providers (`backend/tools/demo_trigger_analytics.py`) — a records ingest alone computes risk *signals* but doesn't yet publish the event that runs that pass automatically (chartered as **analytics.34**). Everything the trigger produces — the alerts, evidence packs, GNN clusters — runs through the real pipeline; only *when* it runs is manual today.
- [ ] Browser tabs open, in this order: `/alerts`, `/investigation/<top-alert-entity>?kb=<kb-id>` (from the `demo-cms` summary), `/dashboard`, `/policy`.
- [ ] Browser zoom bumped to ~110%.
- [ ] Know which role you're demoing as: the **analyst** role lands on Alert Feed (its page set is `dashboard, alerts, investigation, knowledge_bases, rag_chat`); the **supervisor** role lands on Dashboard (`dashboard, alerts, investigation, knowledge_bases, configuration`). Neither role's sidebar carries a "Policy" entry for this pack — see Scene 2.4 for why that's fine. This role picker is a **domain-config UI role** (nav/landing-page only) and is unrelated to the backend RBAC role below.
- [ ] **Only if you're running the optional Act 3 live pack switch:** start the stack with the backend anonymous user elevated to `admin` — `CHILI_DEV_ANONYMOUS_ROLE=admin make dev` (same mechanism `make test-e2e` uses with `=analyst`). Without it, the default anonymous role is `viewer`, the Configuration page's Pack Switcher section is gated on the RBAC `admin` role and will not render, and there is no in-app way to elevate role mid-session — it has to be set before the stack starts. If you're not doing the live switch, skip this and demo as `viewer`/`analyst` normally.

**One-sentence positioning to internalize:**
> "chiliAI turns a flagged pattern into a defensible case — the anomaly, the network it sits in, the plain-language reasoning behind the score, and the policy citation that grounds it — on one screen, driven entirely by a configuration file, not a rewrite."

---

## The Story Arc (Three Acts)

| Act | What you show | What the audience feels |
|-----|---------------|--------------------------|
| **Act 1 — The Problem** | Nothing. You talk. | "I recognize this pain." |
| **Act 2 — The Detection** | Dashboard → Alert Feed → Workbench dossier → Policy | "That's a real, working system." |
| **Act 3 — The Bridge** | (Optional) live domain-pack switch to Air Force housing | "The pack, not the code, is what changed." |

---

## Act 1 — The Hook (45 seconds, no clicks)

**Say this:**

> "I want to ground this in real numbers before I click anything. What you're about to see is running against a genuine 1% sample of CMS's public DE-SynPUF Medicare claims data, resampled to Tennessee: **157,061 provider NPIs**, **113,181 beneficiaries**, and roughly **47,000 carrier claims** plus smaller inpatient and outpatient feeds. This isn't a mockup with placeholder numbers typed into a spreadsheet — it's the same ingestion, graph, analytics, and policy pipeline that would run against a full production feed, just scaled down so the ingest finishes in minutes instead of hours.
>
> The pitch is simple: an investigator today builds a case by hand — pulling the claim, checking whether the provider is really an outlier, checking who else is connected to them, and finding the regulation that applies. **What if the system had already assembled that case, using nothing but data it can actually show you on screen?**
>
> Let's look."

---

## Act 2 — The Detection (≈ 6:15)

### Scene 2.1 — Dashboard | ~65 seconds

**[Click: Dashboard — supervisor's landing page, or navigate there directly]**

**Say this:**

> "This is the operational overview. The top band is four live KPIs pulled straight from the backend for the active knowledge base: active alerts, high-risk entities, entities monitored, and recent workflow runs — no canned numbers, whatever the KB actually holds.
>
> Below that, **Severity Mix** — the current alert queue broken down by severity, straight from the alerts API — and a lead case card that's the same risk-numeral treatment you'll see again in a minute.
>
> One more tab: **Policy Signals.** This shows the top-risk entities in this KB, the metric trend for claim volume, and — when the graph-neural-network capability is on, which it is for this pack — a live **graph clusters** panel. Each cluster gets a colored swatch; that's not decorative, it's the exact same color the graph canvas in the workbench uses for that community — so a cluster you see here is visually the same cluster you'll see there. The count and anomaly scores you see are whatever the current run produced — I'm not going to quote a number here because it changes with the data ingested."

---

### Scene 2.2 — Alert Feed | ~55 seconds

**[Click: "Alert Feed" in the sidebar]**

**Say this:**

> "This is the investigator's triage queue. Every row leads with a risk numeral — the same 0–100 confidence score, just given a bigger typographic treatment — and a mono flag label built directly from the alert's own analytic tags. These aren't hand-written categories: a label like **`TIMESERIES-ANOMALY:WEEKLY-CARRIER-BILLING-SELF · WEEKLY-CARRIER-BILLING`** is literally the top risk factor names the backend computed for that provider, upper-cased and joined. If the underlying signal changes, the label changes with it — there's no copywriter in the loop."

**[Click: "Ack" on a row]**

> "One more thing worth fifteen seconds: acknowledgement here is durable — it's written to a persistent alert-history table, not held in a browser tab or an in-memory cache. If I acknowledge this alert, restart the worker, and reload this page, it is *still* acknowledged. That matters more than it sounds like it should, the first time an investigator loses a day of triage state to a restart."

---

### Scene 2.3 — Investigation Workbench: The Dossier | ~3:30 (the centerpiece)

**[Click: "Investigate entity" on the top alert row]**

**Say this:**

> "This is the entity dossier — where the story lives. At the top: the entity's identity, resolved through the domain configuration so the labels are always correct for whatever pack is active. Next to it, the **risk numeral** — the same large Oxanium-face treatment as the triage rows, but a fixed 46-pixel display size here, because this is the one number the whole page hangs off of — with a confidence bar underneath.
>
> Right below the header: this cyan-tinted band is the **AI ANALYSIS** band — it lists every risk signal that contributed to this score, each with a plain-language rationale and a signed bar: red bars push risk up, green bars pull it down. This is real backend output — the factor names and rationale text come straight from the risk-scoring service, not from a script."

**[Click: "Signals" tab, if not already active]**

> "**Signals** tab: the anomaly trend for this entity's underlying metric, with the actual anomalous points marked in red — those are the real detected anomalies from the time-series analytics, not a stylized illustration. Below the chart, the full factor list with contribution bars."

**[Click: "Network" tab]**

> "**Network** tab: the graph neighborhood around this entity, rendered live from the graph database. When cluster data exists for this knowledge base, nodes are colored by community instead of by entity type — same color vocabulary as the dashboard swatch you just saw — and this membership panel lists every cluster with its size and anomaly score. Click a cluster and its members highlight in the canvas. This is what lets an investigator see 'this isn't one bad actor, it's a connected group,' straight from the graph, not from a narrative someone wrote."

**[Click: "Policy" tab]**

> "**Policy** tab: any policy item that names this specific entity, filtered live from the policy workspace — I'll come back to where those items come from in a second."

**[Click: "Evidence" tab]**

> "And **Evidence** — this is where the newest capability shows up. The lead element is the **AI NARRATIVE** band: a generated summary that reads the evidence items and writes the case in plain language. Underneath it, when the backend's attribution engine has run, you get **signed feature-attribution bars** — this is a real SHAP-style explanation of which inputs pushed the score up or down, and by how much. Below that: the same subgraph, the contributing evidence items, and the policy citations attached to this specific pack."

*(If asked "is that narrative really an LLM?" — hold the answer for Scene 2.4's objection handling below; don't get pulled into it mid-flow.)*

---

### Scene 2.4 — Policy: "Why This Is Defensible" | ~75 seconds

**[Click: address bar, navigate to `/policy` — or click "Open in policy workspace" from the panel you just saw]**

**Say this:**

> "One honest note before I show this: this pack's navigation doesn't put a 'Policy' link in the sidebar for either role today — you get here through a link inside the entity or alert view, or by typing the URL, which is exactly what I just did. It's not hidden, it's just not wired into the left rail yet.
>
> This is the policy workspace. Every item here was generated by one of four configured rule packs — none of this is hardcoded logic, it's YAML. Three are fraud rules: **Elevated payment claims** flags individual high-dollar claims against a review threshold. **Outlier billing concentration** flags providers whose composite risk score — the same score you saw on the dossier — crosses an analyst-review line; this is our stand-in for the classic upcoding pattern. **Referral-ring exposure** flags providers who've been repeatedly flagged across multiple analytics runs — our proxy for a coordinated scheme, driven by an alert-count property the graph pipeline writes back onto the entity itself. The fourth, **graph-scale watch**, is operational rather than fraud-focused — it fires once the knowledge base crosses an entity-volume line, so you'll see its single item in this queue too.
>
> Every item carries its policy citation — chapter, source reference, and excerpt — plus a triage action: accept, reject, defer, or escalate. And when a **critical**-severity item — that's referral-ring exposure — attaches to an entity you're viewing, you get this amber **POLICY SIGNAL** callout right in the workbench. That's the moment that says 'this isn't just an anomaly, it's a named regulatory pattern with a citation attached.'"

---

## Act 3 — The Bridge (optional, ≈ 2 minutes)

### Scene 3.1 — The Domain-Pack Thesis | ~45 seconds (verbal, no clicks)

**Say this:**

> "Everything you just saw — the entities, the labels, the rule packs, the citations — came from one YAML file: `medicare_fraud_cms_desynpuf.yaml`. Nothing you saw is hardcoded to Medicare. If I skip the rest of this section, take that claim on faith from the architecture; if we have two more minutes, I'll show it."

### Scene 3.2 — Live Pack Switch (optional) | ~75 seconds

**[Click: Configuration → Pack Switcher → Activate (department_air_force_housing) → Confirm switch]**

**Say this:**

> "This is the real in-app pack switcher, not a terminal call — it lists every domain pack the backend can see, and it's a deliberate two-step: I click **Activate** next to the Air Force housing pack, it asks me to confirm — 'Switch the whole workspace to "Department of the Air Force Housing"?' — and only then does clicking **Confirm switch** actually validate and hot-swap it, live, with no restart."

**[Wait for the swap-result banner]**

> "And there's the result banner confirming the swap. Same backend, same frontend build. Watch the sidebar: the nav is now family-housing routes, not fraud-investigation routes, because this pack doesn't enable the graph-neural-network or peer-stats capabilities and its navigation config simply doesn't route Dashboard, Alerts, or the Workbench at all. **That's not a missing feature — it's a domain pack correctly declaring what it needs.**
>
> One important caveat, and I'll say it out loud rather than let you discover it: switching back has to target `medicare_fraud_cms_desynpuf` specifically, not the bare `medicare_fraud.yaml` pack — that one needs a separate dev-environment overlay file for its storage connections that a live hot-swap doesn't apply. This stack's default pack already is the desynpuf one, so I'm switching back to exactly what we started on."

**[Click: Configuration → Pack Switcher → Activate (medicare_fraud_cms_desynpuf) → Confirm switch]**

---

## Close (20–30 seconds)

**Say this:**

> "What you saw end to end — detection, network context, a generated narrative with signed attribution, and a policy citation with a triage action — came out of a 1% data sample and a config file, not a bespoke build. The question worth exploring is what your program's entity types and governing regulations would look like as that same config file."

---

## Timing Reference

| Segment | Clock |
|---------|-------|
| Act 1 — Hook | 0:00 – 0:45 |
| 2.1 Dashboard | 0:45 – 1:50 |
| 2.2 Alert Feed | 1:50 – 2:45 |
| 2.3 Workbench dossier (Signals → Network → Policy → Evidence) | 2:45 – 6:15 |
| 2.4 Policy workspace | 6:15 – 7:30 |
| Close (if skipping Act 3) | 7:30 – 8:00 |
| **— optional from here —** | |
| 3.1 Domain-pack thesis (verbal) | 7:30 – 8:15 |
| 3.2 Live pack switch | 8:15 – 9:30 |
| Close | 9:30 – 10:00 |

---

## Objection Handling

| Objection | Response |
|-----------|----------|
| "Is that AI narrative actually generated, or is it templated?" | "Honestly: in this dev environment the configured LLM provider is a local echo stub, so what you'll actually see is the deterministic template fallback — the narrative generator is built to degrade to it automatically whenever the LLM response is unusable, by design, so a flaky provider never blocks a case. Point a real provider — OpenAI, Anthropic, a self-hosted model — at the same config field and the narrative comes from that model instead. Nothing else on the page changes." |
| "Are those risk scores and clusters real, or seeded for the demo?" | "Real — they come from the same time-series anomaly detection, peer-deviation, and graph-community pipeline that runs in the worker on every ingest. The only thing 'demo' about this run is the 1% data sample, so it finishes in minutes." |
| "Why isn't there a Policy link in the sidebar?" | "That's an honest current gap, not a hidden feature — this pack's navigation config doesn't route a Policy Intelligence entry yet. You reach it today from a link inside the entity or alert view, or the URL. It's a config change, not a rebuild, when we add it." |
| "What does it take to point this at our program instead of Medicare?" | "The entity types, the rule packs, the policy citations, the navigation, and the role model you saw are all one configuration file. Standing up a new pack means writing that file against your entity schema and your data feeds — the pipeline underneath doesn't change." |
| "Can I act on the AI's output alone?" | "No — everything here is triage support. The policy workspace's own workflow requires an analyst to accept, reject, defer, or escalate every item; nothing auto-resolves." |

---

## Key Numbers to Remember

| Stat | Source | What it shows |
|------|--------|----------------|
| 157,061 provider NPIs | `MANIFEST.json` | Scale of the 1% TN subset |
| 113,181 beneficiaries | `MANIFEST.json` | Scale of the 1% TN subset |
| 47,266 carrier claims / 654 inpatient / 8,072 outpatient | `MANIFEST.json` | Claim-feed composition of the 1% sample |
| 3 configured fraud rule packs (elevated payment claims, outlier billing concentration, referral-ring exposure) | `medicare_fraud_cms_desynpuf.yaml` `policy_rules` | Configured-not-coded detection patterns |
| Active alerts / high-risk entities / entities monitored / workflow runs | Live on screen — Dashboard KPI band | Real-time operational scale |
| Cluster count, anomaly scores, risk numerals | Live on screen — whatever the current run produced | Never quote a fixed number for these |

---

## Presenter Notes: What NOT to Say

- Do NOT say or demo a **Timeline tab** — the workbench has four tabs (Signals, Network, Policy, Evidence); there is no detection-event timeline. It's an explicit phase-2 item with no backing API.
- Do NOT say or demo **peer-comparison bars** ("this provider vs. the p50/p90 peer benchmark") — the risk factors show contribution bars, not a peer-distribution chart. Also phase-2, no backing endpoint.
- Do NOT mention a **Medicaid pack** — it does not exist. The only shipped packs are `medicare_fraud`, `medicare_fraud_cms_desynpuf`, `food_supply_chain`, and `department_air_force_housing`. If asked about a second healthcare payer program, say "that would be a new pack, not a code change" and move on.
- Do NOT claim **predicted (dashed) network links** are visible today — the styling exists in the graph canvas but the backend does not yet write predicted-link data, so this never renders live. Don't gesture at a dashed line that isn't there.
- Do NOT say "the AI detected fraud." Say "the AI flagged a pattern and generated supporting evidence" — every determination in the policy workspace is explicitly subject to analyst triage (accept/reject/defer/escalate).
- Do NOT quote a fixed cluster count, risk numeral, or anomaly score in your prepared remarks — say "live on screen" and let the audience read the actual number, since it depends on the ingest run.
- Do NOT skip the sidebar/Policy-link honesty beat in Scene 2.4 — presenting it as a bug you caught live builds more trust than hoping nobody clicks "Policy" in the sidebar and finds nothing there.

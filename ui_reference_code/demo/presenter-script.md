# IntegrityAI — Presenter Demo Script
**Audience:** Account Executives · Technology Sales  
**Run time:** ≤ 10 minutes  
**Demo environment:** Live UI at `localhost:5173` (or deployed preview link)  
**Version:** v0.1 · April 2026

---

## Before You Start

**Setup checklist (5 min before the room fills):**
- [ ] Browser is open to the Dashboard, Medicare FFS selected in the program switcher
- [ ] Screen mirrored, font size bumped to 110% in browser zoom
- [ ] AI Investigator panel is **closed** (you'll open it live for effect)
- [ ] Anomaly Feed tab is visible in the left sidebar
- [ ] Know your audience: Are they from a health agency, a civil agency, or mixed?

**One-sentence positioning you should internalize before speaking:**  
> *"IntegrityAI takes what currently takes an analyst three days to build by hand — the evidence, the policy grounding, the peer comparison — and puts it on one screen in under two minutes. And it works for any government program that pays out money or grants access."*

---

## The Story Arc (Three Acts)

| Act | What you show | What the audience feels |
|-----|---------------|------------------------|
| **Act 1 — The Problem** | Nothing. You talk. | "I recognize this pain." |
| **Act 2 — The Detection** | Dashboard → Feed → Provider Deep-Dive | "That is actually impressive." |
| **Act 3 — The Bridge** | Policy Analysis → pivot to State Dept | "Wait — we have this exact problem." |

---

## Act 1 — The Hook (60 seconds, no clicks)

> *Stand still. Don't touch the mouse yet.*

**Say this:**

> "I want to start with a number. The federal government processes over **one billion claims and payments** every year across Medicare, Medicaid, grants, contracts, and benefits programs. Of those, CMS alone estimates that **$100 billion** — with a B — is lost to fraud, waste, and abuse. Every year.
>
> The reason that number hasn't moved in decades isn't a lack of data. Agencies have enormous amounts of data. The reason is that the tools haven't kept up. Traditional systems fire an alert when a provider crosses a threshold. They don't tell the investigator *why* it's suspicious. They don't show how it connects to other actors. And they don't link the finding to the regulation that was violated.
>
> So the investigator gets a list of names. And then spends three days building the case by hand — pulling claims, checking peer comparisons, digging through policy manuals — before they can take a single action.
>
> **What if the case was already built for them?** That's what you're about to see."

**[Engagement moment #1]**
> "Before I click anything — **how many of you have seen an investigator's workload?** Or been in a room where someone said 'we know the fraud is there, we just can't prove it fast enough'?"  
*(Pause for 5–8 seconds. Nod at responses. Don't wait for a full discussion — acknowledge and move on.)*

---

## Act 2 — The Detection (≈ 5 minutes)

---

### Scene 2.1 — The Command Center (Dashboard) | ~75 seconds

**[Click: Dashboard is already open, Medicare FFS selected]**

**Say this:**

> "This is the program operations view. Let's orient quickly. Top line: **3,241 providers** currently flagged. Projected savings from resolved cases: **$52.7 million** this fiscal year. AI confidence across those detections: **88%**.
>
> But here's what I want you to notice — this trend line. Anomaly detections are rising every month, but so are resolutions. The system isn't just finding more problems — it's helping investigators **work through them faster**.
>
> Down here in the breakdown: billing pattern anomalies are the biggest bucket — 1,200-plus cases. Network anomalies — coordinated fraud rings — are the second largest. These are the hard ones. The ones that look clean if you look at a single provider in isolation."

> "One program selector at the top — flip it to Medicaid and the entire dashboard recalibrates. Same platform, different domain pack. We'll come back to why that matters in a minute."

*(Switch to Medicaid briefly so they see the numbers change, then switch back to Medicare.)*

---

### Scene 2.2 — The Anomaly Feed | ~45 seconds

**[Click: "Anomaly Feed" in left sidebar]**

**Say this:**

> "This is the investigator's triage queue. Every row is a flagged entity, ranked by risk score. The AI has already done the prioritization. Highest risk at the top.
>
> Notice the flag labels — these aren't vague 'anomaly detected' alerts. They say *what* the anomaly is: 'UPCODING · HCPCS CONSOLIDATION,' 'REFERRAL RING DETECTED,' 'PHANTOM BILLING INDICATORS.' The investigator knows immediately what kind of case they're looking at before they open it.
>
> Let's go into the number-one case."

**[Click: "Review" on row 1 — Advanced Pain Specialists, Risk 94]**

---

### Scene 2.3 — Provider Deep-Dive: The Story | ~3 minutes

**[Now on the Provider Deep-Dive for Advanced Pain Specialists]**

**Say this:**

> "Advanced Pain Specialists. Miami. Risk score: 94 out of 100. Estimated exposure: **$2.1 million**. The AI has already surfaced the key flags: UPCODING and HCPCS CONSOLIDATION.
>
> Let's see what that actually means."

**[Click: "Billing Patterns" tab]**

> "This is the billing pattern view. Look at this chart — **code diversity over time**. In early 2023, this provider was billing across 47 different procedure codes. Normal for a pain management practice. Then — notice this line — in July 2023, something changes. The code count starts collapsing. By early 2024: **6 codes**. 98% of all billing concentrated in three high-reimbursement codes.
>
> Now look at this bar chart. Most pain specialists use the 99215 code — highest-complexity office visit — about 18% of the time. This provider: **78%** of all visits. They're in the top 1.3% nationally. **Before July 2023, they were completely normal.**"

**[Pause — let that land.]**

**[Engagement moment #2]**
> "Quick show of hands — **who here has seen a pattern change like this and NOT been able to prove it was intentional?** That's the gap we're closing."  
*(Acknowledge the hands, keep moving.)*

**[Click: "Network" tab]**

> "This is where it gets interesting. The system didn't just look at this provider in isolation. It looked at their co-billing relationships — who shares patients with them. We've got four other flagged entities connected here. Sunrise Medical Group has a **34% patient overlap**. Premier Diagnostics, Coastal Rehab.
>
> This isn't one bad actor. This is a network. And every node in that network is already flagged."

**[Click: "Timeline" tab]**

> "And here's the smoking gun. July 15, 2023: **ownership transfer**. Pain Management Holdings LLC takes over. Eight weeks later: the AI detects the first code diversity drop. Twelve months later: billing pattern is completely different from what it was for 16 months prior.
>
> The AI didn't just flag the anomaly. It **pinpointed the trigger event.** That's the difference between a suspicion and a case."

---

### Scene 2.4 — Policy Analysis: The "Why This Is Defensible" | ~90 seconds

**[Click: "Policy Analysis" tab]**

**Say this:**

> "This is the capability that nobody else has. Every signal we just looked at has been automatically queried against the **Policy Knowledge Graph** — a structured index of CMS billing guidance, federal statutes, OIG work plans, and coding standards.
>
> For the HCPCS consolidation signal: the system retrieved three policy sections. CMS IOM §30.6.1 says documentation must support every code selection. NCCI policy flags systematic billing at maximum units. OIG's own FY2024 Work Plan explicitly calls out post-acquisition billing shifts in pain management as a enforcement priority.
>
> The AI's determination: **LIKELY VIOLATION. 91% confidence.** And it tells you exactly what to do next — prepayment edit, records request, overpayment demand.
>
> But notice this yellow callout at the bottom: **POLICY GAP IDENTIFIED.** IOM §30.6.1 doesn't define a numeric threshold for what code concentration ratio is 'too high.' That's an ambiguity in the regulation itself. The system is surfacing that gap to program leadership so CMS can push for a rulemaking fix. **That's a capability no rulebook checker or anomaly score can give you.**"

**[Engagement moment #3]**
> "I want to pause here. What you just saw — the detection, the peer comparison, the network, the policy citation, the recommended action — that's what one investigator used to take **three days** to assemble. This screen took about two minutes. **Does that change how you think about investigator capacity?**"  
*(Allow one or two responses. Pivot immediately after.)*

---

## Act 3 — The Bridge (≈ 2 minutes)

---

### Scene 3.1 — The Pivot: "Same Patterns, Different Program" | ~90 seconds

> "Now I want to make a bigger point — because everything you've seen was built for Medicare claims. But the underlying pattern we just traced has nothing to do with Medicare specifically. Let me say that again: **the pattern has nothing to do with Medicare.**
>
> What did we actually observe?
>
> One — an entity **changes ownership or management**, and immediately its behavior shifts.  
> Two — it **concentrates activity** into a narrow, high-value band rather than a normal distribution.  
> Three — it operates inside a **coordinated network** of related entities that look independent on the surface.  
> Four — it exploits **ambiguity in the governing rules** to stay just inside the threshold of automatic review.
>
> Where else have you seen that pattern?"

**[Pause. Let the room answer silently.]**

> "**Department of State.** Specifically: foreign entity integrity. Let me walk you through what this looks like outside of healthcare."

---

### Scene 3.2 — The Department of State Use Case | ~75 seconds

> *(You don't click anything here — this is a narrative bridge you deliver verbally, connecting what they just saw to the new context.)*

**Say this:**

> "Imagine you're not looking at a pain management practice. You're looking at a **foreign NGO that the State Department funds through a grant program.** Or a **foreign contractor on a procurement vehicle.** Or an entity sponsoring visa applications in bulk.
>
> Now apply the same four patterns:
>
> **Ownership change trigger:** A previously legitimate organization changes its board or beneficial ownership — and within months, its grant expenditure patterns shift. Before: broad programmatic spending across multiple line items. After: consolidated into narrow, high-margin line items that are harder to audit. The **HCPCS consolidation chart** you just saw — replace 'billing codes' with 'grant expenditure categories.' The curve is identical.
>
> **Peer outlier:** That entity is now approving or disbursing at rates that are statistical outliers compared to similar grantees in the same region and program type. Same peer comparison engine. Different data.
>
> **Network analysis:** Pull the map of related entities — shared beneficial owners, shared bank accounts, shared signatories. You get the same referral ring topology you just saw in Miami inside a foreign contractor network. Except instead of a kickback arrangement, it may implicate **FARA, ITAR, or OFAC sanctions.**
>
> **Policy Knowledge Graph:** Instead of querying CMS billing guidance, the graph is loaded with 22 CFR, Export Administration Regulations, FARA filing requirements, the OFAC sanctions list, and State Department procurement regulations. The AI cites the specific regulatory section. The determination is still auditable, still defensible, still traceable."

**[Pause one beat.]**

> "The only thing that changes between Medicare FFS and a State Department foreign entity program is the **domain pack** — the set of entities, features, and policy documents loaded into the system. The detection engine, the peer comparison, the network analysis, the policy grounding, the investigator workflow — **identical.** That's the architectural bet we made. And that's why this platform accelerates capability for any agency with a financial integrity or entity screening mandate."

---

## Close (30 seconds)

**Say this:**

> "We're at the early stages of a conversation across the federal government about what it actually looks like to deploy AI in high-stakes enforcement environments — where the AI is not making decisions, but giving investigators **the case they need to make the right decision faster.**
>
> The accelerator you saw today took a Medicare use case to production-ready prototype in weeks, not years. The same framework is ready to be applied to your agency's domain.
>
> **The question for us to explore together is: what's the use case you're sitting on right now where you know the exposure is real, but you can't investigate fast enough?** That's the conversation I want to have."

**[Engagement moment #4 — Close on a question]**
> "I'll open it up: **What entity types or program areas come to mind for your agency?**"  
*(This is your discovery question. Listen. Take notes. Don't pivot to features.)*

---

## Timing Reference

| Segment | Clock |
|---------|-------|
| Act 1 — Hook + audience question | 0:00 – 1:00 |
| Dashboard | 1:00 – 2:15 |
| Anomaly Feed | 2:15 – 3:00 |
| Provider Deep-Dive (Billing + Network + Timeline) | 3:00 – 6:00 |
| Policy Analysis + audience question | 6:00 – 7:30 |
| The Bridge — Medicare → DoS | 7:30 – 9:30 |
| Close + discovery question | 9:30 – 10:00 |

---

## Objection Handling

| Objection | Response |
|-----------|----------|
| *"This looks like an anomaly detection tool we already have."* | "What you probably have is a rules engine that fires when a threshold is crossed. The difference here is twofold: the AI explains *why* the pattern is suspicious by comparison to peers *and* by citation to policy. And it generates the next action. That's the gap between an alert and a case." |
| *"We're worried about false positives. We can't act on AI output alone."* | "We designed this explicitly for that concern. Every determination on screen says 'triage support, not a final decision.' The AI builds the case. The investigator makes the call. The human is always in the loop — and the system captures their feedback to improve future detections." |
| *"What does it take to configure this for our program?"* | "That's the domain pack concept. We need your entity schema, your key data sources, and your governing regulatory corpus. We've built the process to take that from a structured discovery engagement to a working prototype. The Medicare pack you saw today is the template." |
| *"Is the data secure? We can't send claims data outside our environment."* | "The platform can be deployed entirely within your agency's boundary — on-prem, Azure Government, or AWS GovCloud. No data leaves your environment. The policy corpus is air-gapped within the deployment." |
| *"How is this different from a COTS fraud detection tool?"* | "COTS tools are tuned for healthcare or financial services. They don't understand State Department grant regulations or ITAR. The Policy Knowledge Graph is loaded with your agency's regulatory corpus — that grounding is the differentiator. It's the difference between flagging something unusual and knowing whether it's a violation." |

---

## Key Numbers to Remember

| Stat | What it shows |
|------|--------------|
| $100B/year estimated federal fraud exposure | Stakes — why this matters |
| 3,241 flagged providers, $52.7M savings (demo) | Scale of detection |
| 88% AI confidence | Precision — not a false-positive engine |
| 47 → 6 codes: billing concentration jumps to 98% | The specific, visible anomaly |
| 78% vs. 18%: 99215 rate vs. peer median | Peer comparison power |
| 4 co-flagged network partners | Network detection reach |
| 91% determination confidence, 3 policy citations | Defensible, auditable output |
| Same platform: change only the domain pack | Cross-agency portability |

---

## Presenter Notes: What NOT to Say

- ❌ Don't say "the AI detected fraud." Say "the AI flagged a pattern consistent with fraud." The human investigator makes the final determination.
- ❌ Don't get into the model architecture unless asked directly. The magic is the *workflow*, not the model.
- ❌ Don't demo the Case Management or Policy Intelligence screens unless someone asks. Stay in the Provider Deep-Dive — that's where the story lives.
- ❌ Don't over-explain the UI. You're selling outcomes, not features.
- ❌ Don't say the State Dept use case is "live" or "deployed." It's a pattern extension. Frame it as "the framework is ready — the domain pack is the configuration layer."

---

## For Longer Demos (15–20 min add-ons)

If the audience is engaged and you have more time, these screens close the deal:

**Option A — Policy Intelligence (CMS Leadership view)**  
> "Let me show you one more screen — this one's for program leadership, not investigators."  
Navigate to Policy Intelligence. Walk through the policy gap analysis table. The hook: *"The AI is not just finding violations — it's finding where the law itself is ambiguous. That feeds directly into rulemaking."*

**Option B — AI Investigator Panel**  
> "Let me show you something your investigators would actually use every day."  
Open the AI chat panel from the bottom-right. Ask it: *"Why was this provider flagged? What should I look at first?"* Let the audience watch it respond in context. The hook: *"This is the AI as a case partner, not a black box."*

**Option C — Switching Domain Packs Live**  
> "You asked about your specific program — let me show you how fast this reconfigures."  
Switch the program selector from Medicare to Medicaid. Walk through how the KPIs, trend data, and feed categories all shift. The hook: *"Different payer, same platform, 30-second reconfiguration."*

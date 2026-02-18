
# > Ship accelerator v0.1 with evaluation gates + monitoring plan included by default (this shifts you into decision authority rather than content production).

Tell me more about accelerator I need build. What format? Code , template, diagram, etc. where to start?

An “accelerator” in your world is a **versioned delivery kit** that lets any account team implement a specific AI-enabled workflow in an agency’s AWS/Azure environment fast, safely, and repeatably—*with built-in evaluation gates and a monitoring plan*. OMB M‑25‑21 explicitly pushes agencies toward AI-enabling infrastructure across the lifecycle (development, testing, deployment, continuous monitoring) and toward ongoing testing/validation plus post-award monitoring of AI performance, especially for high-impact AI.

## What format should the accelerator be?

Think “product release,” not “a deck.” The minimum viable accelerator (v0.1) should include these artifact types:

- **Playbook (docs):** A short, step-by-step implementation guide (who does what, prerequisites, timeline, and definition of done).
- **Reference architectures (diagrams):** One Azure and one AWS target architecture, including identity, network boundaries, data flow, logging/monitoring, and where model/LLM components run.
- **Templates (governance + delivery):**
    - Use-case intake form (problem, users, decision impact, data sources, constraints).
    - Risk classification + “high-impact AI” screening checklist (because M‑25‑21 defines high-impact AI around outputs that are a principal basis for decisions with legal/material effects).
    - Model/GenAI documentation template (capabilities/limitations, intended use, out-of-scope use, human oversight).
    - Data provenance template (sources, access approvals, retention, PII/PHI handling).
- **Code starters (optional but powerful):** Not a full product—just enough scaffolding to make delivery fast: repo structure, sample config, deployment scripts/IaC skeleton, and a small “hello world” pipeline that teams can extend. M‑25‑21 encourages reuse/sharing of custom-developed code and assessments where practicable (with exceptions for security/privacy/mission risks).
- **Evaluation harness (must-have):** A standardized way to test quality before go-live (test set format, acceptance criteria, error taxonomy, red-team prompts for GenAI, and sign-off workflow).
- **Monitoring plan (must-have):** What you log/measure, who reviews it, thresholds, incident response, and a rollback/discontinue plan—M‑25‑21 requires minimum risk management practices for high-impact AI and states agencies must have a plan to discontinue use if performance is not appropriate.


## Where to start (the fastest path)

Start with **one workflow** and one “thin slice to production,” then generalize.

1) Pick the workflow + boundary

- Example boundary: “Case triage copilot for program-integrity analysts” (summarize case notes, retrieve policy references, propose next-best actions), explicitly *not* “make final enforcement decisions.”

2) Write v0.1 “definition of done”

- Include: deployed in client tenant, identity + access approved, evaluation passed, monitoring live, and a weekly review cadence.

3) Build the evaluation + monitoring first
This is the core of “decision authority.” You want every team to ship with the same gates:

- Pre-prod gates: accuracy/quality threshold on a representative test set, privacy/security checks, human-in-the-loop design confirmed.
- Post-prod gates: monitoring dashboards, drift checks, misuse detection, and a documented discontinue/rollback plan.

4) Then build the reference architecture + templates
Once you know the gates, your architecture and templates become obvious (what logs you need, what data provenance you must capture, what security controls are non-negotiable).

## What “v0.1” should look like (concrete deliverables)

If you want a crisp starting package, aim for a repo + a short doc set:

- `/docs/README.md` (2–4 pages): scope, prerequisites, timeline, roles, definition of done.
- `/docs/architecture-azure.pdf` + `/docs/architecture-aws.pdf` (1 diagram each).
- `/templates/` (Word/Markdown): intake form, risk screening, model/GenAI card, data provenance, go-live checklist.
- `/eval/` (CSV + notebook): gold test set format, scoring rubric, acceptance thresholds, error taxonomy.
- `/monitoring/` (Markdown): telemetry contract (logs/metrics), review cadence, incident workflow, rollback/discontinue criteria.


## A practical first week

- Day 1: Choose the workflow and write the scope + out-of-scope boundaries.
- Day 2: Draft the evaluation rubric and acceptance thresholds.
- Day 3: Draft the monitoring plan + discontinue/rollback triggers (even if rough).
- Day 4–5: Create the Azure and AWS reference architecture diagrams that satisfy the monitoring/eval needs.

If you tell me which specific program-integrity workflow you want for v0.1 (case triage, network risk, document intake/RAG, etc.), I’ll propose an exact v0.1 package (file list, templates, and the first 10 acceptance criteria) tailored to that workflow.

---

# Use the CMS crushing fraud chili cook-off solution as the use case. Which program-integrity workflow does it cover? think of expanding the explainable AI techniques, including knowledge graph, graph learning and time series based anomaly detection to broader healthcare domain, include claims (Medicare, Medicaid) and enrollment (healthcare marketplace agent/broker, etc. ) and more.

The CMS Crushing Fraud Chili Cook-Off use case primarily covers the program-integrity workflow of turning **Medicare FFS claims anomalies** into explainable, reviewable fraud indicators that help teams prioritize investigations and detect broader patterns beyond one-off bad actors.  Phase 2 specifically centered on Medicare FFS Hospice, Part B, and DME claims (via CMS Limited Data Sets), with external teams asked to apply explainable AI/ML to find anomalies/trends and propose scalable analytic and policy solutions.[^22_1]

## What workflow it covers

At its core, the Chili Cook-Off maps to a “claims-based detection → indicator generation → investigator prioritization” workflow, with an explicit requirement for explainable AI and humans meaningfully in the loop.  CMS also emphasized moving past “pattern detection alone” by understanding underlying drivers so anomalies can be translated into evidence-based indicators that can be used to proactively flag similar schemes at scale.[^22_2]

## Expand to broader healthcare

You can generalize the same workflow to a cross-program “entity risk + scheme discovery + trend monitoring” capability spanning claims and enrollment, because the underlying problem remains: detect unusual patterns, explain why, and convert into repeatable indicators and actions.  The original competition data scope (2022–2024 SAF LDS for Medicare FFS Hospice/Part B/DME, random 5% sample) is a good template for defining “minimum viable” data slices in new domains (e.g., Medicaid claims, Marketplace enrollment/broker activity) so expansion is structured rather than ad hoc.[^22_2]

## Explainable AI expansion

To expand explainability beyond “why this provider scored high,” design for three explainability layers:

- Indicator-level explainability: human-readable rules or narratives that justify an indicator and its intended use (what it flags, what it does not flag).
- Network-level explainability (knowledge graph + graph learning): show the minimal set of relationships (subgraph) that drives a suspicious cluster or coordinated behavior pattern.
- Temporal explainability (time series anomaly): explain “what changed” relative to a baseline (seasonality, peer group, policy change windows), not just that it’s statistically odd.


## Where to start (your accelerator v0.1)

Start by defining the accelerator around **one reusable workflow**: “entity risk scoring + scheme clustering + indicator publishing,” because that matches what CMS asked contestants to do (anomalies/trends → novel indicators → scalable solutions).  Then build the minimum deployable kit as a versioned package (docs + templates + reference architectures + evaluation/monitoring) that an account team can apply to Medicare, Medicaid, or Marketplace-style datasets with configuration—not reinvention. If you tell me which “next domain” you want first (Medicaid claims vs Marketplace broker/enrollment), I’ll propose the exact entity/edge model for the knowledge graph and the first 10 indicators to implement.[^22_2]
<span style="display:none">[^22_10][^22_11][^22_12][^22_13][^22_14][^22_15][^22_16][^22_17][^22_3][^22_4][^22_5][^22_6][^22_7][^22_8][^22_9]</span>

<div align="center">⁂</div>

[^22_1]: https://www.thomsonreuters.com/en/reports/2026-ai-in-professional-services-report

[^22_2]: https://www.slalom.com/us/en/insights/government-outlook-2026

[^22_3]: https://www.cms.gov/priorities/crushing-fraud-waste-abuse/overview/crushing-fraud-chili-cook-competition

[^22_4]: https://www.cms.gov/fraud

[^22_5]: https://www.vgm.com/communities/what-do-cms-fraud-efforts-mean-for-dme/

[^22_6]: https://www.linkedin.com/posts/stacie-buck-radrx_cms-launches-chili-cook-off-competition-activity-7366921571707326464-l4nw

[^22_7]: https://orangeslices.ai/cms-launches-crushing-fraud-chili-cook-off-competition/

[^22_8]: https://www.amida.com/cms-selects-amida-as-a-finalist-in-the-crushing-fraud-chili-cook-off-competition/

[^22_9]: https://www.morningstar.com/news/business-wire/20251223398078/milliman-wins-cms-crushing-fraud-chili-cook-off-competition

[^22_10]: https://www.nextgov.com/artificial-intelligence/2025/08/cms-launches-chili-cook-competition-source-ai-can-detect-fraud/407698/

[^22_11]: https://finance.yahoo.com/news/milliman-wins-cms-crushing-fraud-140000176.html

[^22_12]: https://finance.yahoo.com/news/cms-selects-amida-finalist-crushing-171000151.html

[^22_13]: https://www.beckershospitalreview.com/healthcare-information-technology/ai/cms-launches-chili-cook-off-ai-competition-to-tackle-medicare-fraud/

[^22_14]: https://govciomedia.com/cms-uses-explainable-ai-to-strengthen-medicare-fraud-detection/

[^22_15]: https://www.abtglobal.com/news/news-releases/abt-named-finalist-in-cms-crushing-fraud-innovation-challenge

[^22_16]: https://www.abtglobal.com/insights/events/cms-crushing-fraud-chili-cookoff-showcase-2025

[^22_17]: https://www.linkedin.com/pulse/cms-chili-cook-off-strategic-analysis-ai-driven-medicare-zoy0f


---

# next domains include marketplace enrollment fraud related to agent/broker, and Medicaid claims (certain claims types like dental or vision) .

Your Chili Cook-Off–style accelerator maps best to a repeatable workflow of **(1) detect anomalies → (2) connect entities into suspected schemes → (3) generate explainable indicators → (4) prioritize/route to human action → (5) monitor for recurrence and drift**. That same workflow expands cleanly into Marketplace agent/broker enrollment integrity and Medicaid dental/vision claims, as long as you treat them as two new “domain packs” on top of a shared explainable-AI core.

## Domain workflows to cover

Marketplace (agent/broker): the workflow is **unauthorized enrollment / unauthorized plan switch detection and prevention**, plus broker/entity oversight and casework prioritization. CMS described blocking agents/brokers from changing enrollments unless already associated with the consumer’s enrollment, using a three-way call for exceptions, and suspending 850 agents/brokers for suspected unauthorized enrollments/plan switches (with large volumes of related complaints in 2024).[^23_1]

Medicaid dental/vision claims: the workflow is **provider/network risk + claim pattern anomaly detection + case generation** (often state/MCO-specific), where the “unit of action” is a provider, clinic, group, or beneficiary segment. OIG reports Medicaid Fraud Control Units operate in all states/territories and in FY2024 reported 1,151 convictions and \$1.4B recoveries, supporting the need for scalable analytics across Medicaid program integrity.[^23_2]

## Knowledge graph expansions

Build one canonical KG core, then plug in domain-specific entity/edge sets.

Marketplace KG (agent/broker misconduct)

- Entities: Consumer, Application, Enrollment, Plan/Issuer, Agent/Broker (NPN), Web-broker/EDE entity, Consent event (call-center/attestation), Complaint, Device/IP, Address/Phone/Email, Commission payment.
- Edges: assisted_by, modified_by, switched_to, associated_with (agent↔consumer), complaint_against, shared_device/contact/address, commission_paid_to, consent_verified_via.
- High-value graph outputs: suspicious broker “pods” (shared device/contact across many consumers), abnormal switch cascades, and EDE funnels with high complaint linkage.

Medicaid dental/vision KG (claims integrity)

- Entities: Beneficiary, Rendering provider (NPI), Billing provider/group, Location, Procedure code (CDT/CPT/HCPCS), Diagnosis, Ordering/referring provider, Prior auth (if present), MCO/State program segment.
- Edges: treated, billed, referred_by, performed_at, shared_address/phone/bank (provider link analysis), co-occurs_with (procedure bundles), temporal_sequence (service trajectories).
- High-value graph outputs: clinic rings (shared addresses/bank accounts), improbable referral/ordering patterns, and “code-bundle communities” that deviate sharply from peer groups.


## Explainability + evaluation “by default”

For each detected risk, require three explanations in your accelerator:

- Local: “Why this entity is high risk” (top features + temporal deltas + nearest-peer comparison).
- Network: “What connections matter” (smallest suspicious subgraph and which edges drove the score/cluster).
- Temporal: “What changed” (change-point / seasonality-adjusted spike narrative).

Then make this testable: ship an evaluation harness that checks (a) precision-at-K for case queues, (b) stability over time, and (c) explanation quality (can an investigator answer “what would I look at next?” consistently). For Marketplace specifically, ensure the playbook can incorporate operational controls CMS has used (e.g., association gating, consent verification events) as features and as downstream mitigations.[^23_1]

## Where to start (v0.1 build order)

1) **Pick one thin-slice outcome per domain**: Marketplace = “unauthorized switch/enrollment risk queue by broker”; Medicaid dental/vision = “clinic/provider risk queue with ring detection.”
2) Define a common “indicator contract”: every indicator must have name, scope, data prerequisites, reason codes/explanation, investigator next steps, and monitoring metric.
3) Build the KG schema + 10 indicators each domain (start simple): a mix of time-series spikes, peer outliers, and graph-based rings/communities.
4) Only then implement modeling choices (GNN, temporal anomaly models) behind the indicators—so the accelerator remains deployable even when a client can’t run deep learning in their environment yet.

If you tell me which Marketplace dataset access you typically have (HealthCare.gov complaint/case data, EDE logs, enrollment transactions, broker registry/commissions, call-center events), I’ll propose a concrete Marketplace v0.1 indicator list (10 items) and the exact nodes/edges needed for each.
<span style="display:none">[^23_10][^23_11][^23_12][^23_13][^23_14][^23_15][^23_16][^23_3][^23_4][^23_5][^23_6][^23_7][^23_8][^23_9]</span>

<div align="center">⁂</div>

[^23_1]: https://www.cms.gov/newsroom/press-releases/cms-update-actions-prevent-unauthorized-agent-and-broker-marketplace-activity

[^23_2]: https://www.slalom.com/us/en/insights/government-outlook-2026

[^23_3]: https://www.cms.gov/newsroom/fact-sheets/cms-actions-protect-consumers-strengthen-exchange-program-integrity

[^23_4]: https://www.cms.gov/newsroom/fact-sheets/2025-marketplace-integrity-and-affordability-final-rule

[^23_5]: https://www.kff.org/patient-consumer-protections/fraud-in-marketplace-enrollment-and-eligibility-five-things-to-know/

[^23_6]: https://www.cms.gov/files/document/cms-9884-f-2025-pi-rule-master-5cr-062025.pdf

[^23_7]: https://leadingage.org/hhs-oig-to-study-misleading-ma-marketing-practices/

[^23_8]: https://resources.cotiviti.com/fraud-waste-and-abuse/busted-the-top-fraud-schemes-of-q2-2024

[^23_9]: https://chir.georgetown.edu/federal-efforts-ostensibly-aimed-at-marketplace-fraud-ignore-obvious-strategies-to-counter-broker-misconduct/

[^23_10]: https://www.akerman.com/en/perspectives/hrx-dont-be-suspicious-dont-be-suspicious-new-oig-special-fraud-alert-warns-about-suspect-payments-in-medicare-advantage-marketing-arrangements.html

[^23_11]: https://oig.hhs.gov/newsroom/videos/medicaid-fraud-control-units-annual-report-fiscal-year-2024/

[^23_12]: https://shvs.org/wp-content/uploads/2025/06/SHVS_2025-Final-Marketplace-Integrity-Rule.pdf

[^23_13]: https://paragoninstitute.org/private-health/unpacking-the-great-obamacare-enrollment-fraud/

[^23_14]: https://www.kff.org/medicaid/5-key-facts-about-medicaid-program-integrity-fraud-waste-abuse-and-improper-payments/

[^23_15]: https://www.dentonshealthlaw.com/cms-issues-2025-marketplace-integrity-and-affordability-proposed-rule/

[^23_16]: https://oig.hhs.gov/fraud/consumer-alerts/consumer-fraud-health-insurance-marketplace/


---

# In the accelerator v0.1, how to incorporate the process of leveraging SME's knowledge up front to frame the problem, and review/validate/provide feedback to AI's result? think of both the UI/UX and workflow integration perspectives, as well as other considerations to highlight the human elements in this workflow.

In v0.1, you should *treat SMEs as part of the system*, not “stakeholders you interview once.” Concretely: build an SME intake step that produces structured priors (hypotheses, constraints, and acceptable evidence), then build an SME review loop that turns model output into validated indicators, with accountability and monitoring—this aligns with M‑25‑21’s push for governance, ongoing testing/validation, and continuous monitoring across the AI lifecycle.

## Where SMEs show up in the workflow

Design three explicit “human checkpoints,” each with a UI surface and an artifact:

1) Frame (before modeling)

- Goal: convert SME knowledge into structured hypotheses and constraints.
- Artifact: “Indicator candidates + assumptions + constraints” (versioned).

2) Validate (before go-live)

- Goal: test that outputs are meaningful and safe for the intended use; decide thresholds and routing.
- Artifact: “Acceptance criteria + false positive/negative tolerance + reason codes.”

3) Operate (after go-live)

- Goal: continuously evaluate performance, review drift, and decide whether to adjust, pause, or discontinue.
- Artifact: “Monitoring dashboard + weekly triage decisions + change log,” consistent with M‑25‑21’s emphasis on continuous monitoring, ongoing testing/validation, and having a plan to discontinue if performance is not appropriate.


## UI/UX you should implement (minimal but powerful)

You don’t need a full product UI to do this well—v0.1 can be a lightweight web app or even a structured internal tool, as long as it enforces the loop.

SME framing screens (two pages)

- “Use-case canvas” form: decision being supported (not automated), who acts on it, what constitutes harm, what evidence is acceptable, what data is trusted/untrusted.
- “Indicator builder” form: SMEs propose indicators in plain language (e.g., “agent switches many consumers shortly after enrollment”), specify expected directionality, peer group, and “what would convince you it’s real.”

SME review screens (case + indicator views)

- Investigator/SME queue: shows top-K cases with **three explanations** (local features, network subgraph, temporal change) plus the evidence bundle.
- Feedback controls: “Agree/Disagree,” reason codes, severity, recommended next action, and “data issue vs model issue vs policy issue” tagging.

Operations screens (monitoring + governance)

- Drift and stability view: alert when distributions change, when complaint patterns spike, or when precision drops.
- “Indicator health” view: adoption (are people using it), yield (hits per hour), and harm metrics (consumer impact flags).
- Kill-switch workflow: a clearly logged decision to pause/discontinue an indicator/model when performance isn’t acceptable, matching the “discontinue until compliant / cease use if mitigation isn’t possible” language in M‑25‑21 for high-impact AI.


## Workflow integration (how it fits real work)

Make the accelerator integrate into existing casework rather than creating a parallel system.

Marketplace agent/broker example (tying to real controls)

- Your system should output: a broker risk queue and “suspected unauthorized switch/enrollment” cases.
- Human actions should align with operational controls CMS has already used (association gating, consent verification/three-way call pathways, complaint resolution workflows) so SMEs can validate whether the AI’s suggestions map to feasible interventions.[^24_1]

Medicaid dental/vision example

- Output: provider/clinic risk queue, suspicious ring clusters, and code-pattern anomalies.
- Human actions: MFCU referral package, MCO SIU case creation, provider education/edit recommendations—SMEs should confirm what evidence is needed for each downstream action.


## Human elements you should highlight (v0.1 design principles)

- **Accountability by role:** define who can (a) approve an indicator for production, (b) change thresholds, (c) pause it.
- “Two truths” design: SMEs can mark a finding as “real but expected” (policy/seasonality) vs “suspicious,” preventing the model from forcing everything into fraud/non-fraud.
- Capture uncertainty: allow “insufficient evidence” as a first-class label; use it to drive data collection or targeted sampling.
- Train the model with feedback, but safely: separate “label for operations” from “label for training,” and track provenance of feedback.


## Where to start (build order for v0.1)

1) Create the **SME indicator workshop** (2 hours) and capture outputs using your structured forms (use-case canvas + indicator builder).
2) Build the evaluation harness around SME acceptance criteria (precision-at-K target, minimum evidence bundle, explanation requirements).
3) Implement the review UI for top-K cases + feedback capture; this is the fastest way to make SMEs “part of the loop.”
4) Add monitoring and a governance change log.

If you answer these two questions, I’ll propose a concrete v0.1 UI flow (screen list + fields) and the exact SME workshop agenda:

1) For Marketplace, do you have complaint/casework data and broker identifiers (NPN) available at analysis time?
2) Who are your SMEs in practice (program integrity ops, call-center, policy, legal/privacy, or SIU investigators)?

<div align="center">⁂</div>

[^24_1]: https://www.thomsonreuters.com/en/reports/2026-ai-in-professional-services-report


---

# 1 - yes. 2 - program integrity ops, investigators

In accelerator v0.1, bake SMEs into the system via (1) a structured “SME framing” intake that becomes configuration for detection, and (2) a mandatory “SME validation loop” where investigators label outcomes and explanations, driving thresholding, governance sign-off, and monitoring.

## v0.1 human-in-loop blueprint

Design the accelerator around three checkpoints: **Frame → Validate → Operate**, each producing auditable artifacts and decisions. OMB M-25-21 explicitly emphasizes AI lifecycle maturity (development, testing, deployment, continuous monitoring) and ongoing testing/validation, plus a plan to discontinue high-impact AI when performance isn’t appropriate, so your v0.1 should make those steps non-optional.

## UI/UX screens (minimum set)

Build a lightweight web UI (or internal app) with role-based access for program integrity ops and investigators; the goal is fast, consistent feedback capture.

- Screen 1: Use-case canvas (SME framing)
    - Fields: Decision supported (not automated), “what action happens next,” harm/abuse risks, required evidence types, excluded use (out-of-scope), peer group definition, time windows.
- Screen 2: Indicator builder (SME hypotheses → machine config)
    - Fields: Indicator name, natural-language description, target entity (broker / provider / clinic), expected pattern (temporal/network/peer), data prerequisites, initial thresholds, “reason codes” SMEs expect to see.
- Screen 3: Case queue (investigator workbench)
    - Display: risk score + confidence, top reason codes, timeline sparkline, and “network card” (small suspicious subgraph).
    - Actions: Agree / Disagree / Insufficient evidence, reason tags (data issue vs model issue vs expected business process vs policy event), recommended next step.
- Screen 4: Evidence bundle viewer (the trust anchor)
    - Shows: raw enrollment/claim events, complaint linkages, agent/broker association history, and any consent/attestation artifacts available.
- Screen 5: Indicator health + monitoring (ops owner)
    - Metrics: yield (cases/hour), precision-at-K from SME labels, drift alerts, and a “pause indicator / rollback” control consistent with the discontinuation expectations in M-25-21.
- Screen 6: Change log + approvals (governance)
    - Captures who changed thresholds/models, why, what evidence supported it, and effective date; this also supports documentation/provenance expectations in M-25-21.


## SME workflow integration (Marketplace + Medicaid)

Marketplace agent/broker integrity: align your human-in-loop workflow to operational controls CMS has already implemented—e.g., blocking brokers from changing enrollments unless already associated, and using a three-way call exception path—so SMEs can validate that AI outputs map to feasible interventions.  Your casework UI should explicitly capture whether a flagged event appears consistent with unauthorized plan switches/enrollments patterns that CMS tracks via complaints and resolves through casework pipelines.[^25_1]

Medicaid dental/vision: the same UI pattern applies, but “evidence bundle” changes (procedure patterns, location, provider links, utilization trajectories) and “next action” options change (MCO SIU case creation, state PI referral, provider education/edit recommendation). Keep the SME feedback taxonomy consistent across domains so your accelerator learns what’s “suspicious,” “expected,” and “data-quality” in a reusable way.

## Where to start (practical build order)

1) Run a 90-minute SME framing session with PI ops + investigators and produce 10–15 indicator hypotheses (don’t model yet).
2) Convert those hypotheses into your Indicator Builder template and define acceptance criteria (precision-at-K target, minimum evidence required, explanation requirements).
3) Build the Case Queue + Feedback capture UI next (even with a simple baseline model), because that loop is what lets SMEs validate and iterate quickly.
4) Only after feedback is flowing, add advanced methods (knowledge graph features, GNN scoring, time-series change-point detection) behind the same indicator contract.

If you want, I can draft your v0.1 “Indicator Builder” template (field list + examples) specifically for Marketplace agent/broker misconduct using complaint/casework data and broker identifiers (NPN).

<div align="center">⁂</div>

[^25_1]: https://www.thomsonreuters.com/en/reports/2026-ai-in-professional-services-report


---

# with all the information above, draft me the v0.1 accelerator with all the components required.

Below is a complete draft of an **Accelerator v0.1** you can stand up internally as a versioned “delivery kit” (docs + templates + starter code structure + evaluation gates + monitoring + SME workflow + UI screens).

## 1) Purpose, scope, principles

**Accelerator name:** *Crushing Fraud XAI Accelerator v0.1* (Claims + Enrollment Integrity)

**Primary use case (anchor): CMS Crushing Fraud Chili Cook-Off**

- Goal: use explainable AI/ML to detect anomalies/trends in Medicare claims data and translate them into **novel fraud indicators**, while reducing labor-intensive processes and keeping humans meaningfully in the loop.[^26_1]
- Data scope template: Medicare FFS Hospice, Part B, and DME claims (CMS LDS) as the v0.1 reference domain pack.[^26_1]

**Operating principles (non-negotiable)**

- **Human-in-the-loop by design** (SME framing + investigator validation + operational monitoring), consistent with the Chili Cook-Off intent.[^26_1]
- “Lifecycle-ready”: development → testing → deployment → **continuous monitoring**, consistent with federal expectations for AI-enabling infrastructure across the lifecycle.
- “Test/monitor/discontinue”: include ongoing testing/validation and monitoring; have a plan to discontinue high-impact AI use when performance is not appropriate.
- “Document it like you’ll defend it”: document capabilities/limitations and data provenance as standard artifacts.


## 2) Deliverable package (what v0.1 consists of)

### A. Repository / folder structure (deliverable)

Use this exact structure (even if some files are placeholders in v0.1):

```text
crushing-fraud-xai-accelerator/
  README.md
  CHANGELOG.md
  /docs
    00_overview.md
    01_roles-and-raci.md
    02_use-case-canvas.md
    03_data-requirements.md
    04_architecture_azure.md
    05_architecture_aws.md
    06_indicator-contract.md
    07_ui-ux_workflow.md
    08_governance-and-approvals.md
    09_security-privacy.md
    10_release-and-versioning.md
  /templates
    T01_use-case-intake_form.md
    T02_indicator-builder_form.md
    T03_risk-screen_high-impact-ai.md
    T04_model-card_xai.md
    T05_data-provenance.md
    T06_eval-plan_and_acceptance.md
    T07_go-live_checklist.md
    T08_post-go-live_weekly-review.md
    T09_change-request.md
  /domain-packs
    /medicare-ffs_chili
      schema.md
      indicators_v0.1.md
      eval_dataset_spec.md
    /marketplace_agent-broker
      schema.md
      indicators_v0.1.md
      eval_dataset_spec.md
    /medicaid_dental-vision
      schema.md
      indicators_v0.1.md
      eval_dataset_spec.md
  /eval
    eval_harness_spec.md
    testset_format.csv (spec file, can be empty in v0.1)
    scoring_rubric.md
    explanation_quality_rubric.md
  /monitoring
    telemetry_contract.md
    dashboards_spec.md
    drift_checks.md
    incident_runbook.md
    discontinue_pause_policy.md
  /ui
    screens_spec.md
    fields_dictionary.md
    wireframes_lowfi.md (optional)
  /code-starters
    /notebooks
      01_feature_build.ipynb
      02_indicator_scoring.ipynb
      03_explanations.ipynb
    /pipelines
      pipeline_skeleton.md
    /iac
      terraform_skeleton.md
```


### B. What each component must achieve

- **Docs**: make an average delivery team “good enough” without you on every call.
- **Templates**: force standardization (SME framing, risk screening, evidence standards, acceptance criteria, change control).
- **Domain packs**: “configuration + schema + indicator library” per domain, so you expand beyond Medicare without rewriting the accelerator.
- **Eval + monitoring**: the heart of v0.1—this is what makes it productionizable and governable.


## 3) End-to-end workflow + SME integration (UI/UX + process)

v0.1 uses one shared workflow across all domains:

### Stage 0 — SME framing (before modeling)

**Objective:** convert PI Ops + investigator knowledge into structured, testable hypotheses.

**Workshop (90 minutes) output artifacts**

- Completed T01 Use-case intake form
- 10–15 drafted indicators using T02 Indicator Builder
- Draft “evidence bundle requirements” (what investigators must see to trust it)

**UI/UX screens**

1) *Use-case Canvas* (PI Ops lead owns)
2) *Indicator Builder* (SMEs propose indicators; product owner approves into backlog)

### Stage 1 — Build indicators (baseline first)

**Objective:** implement indicators in a model-agnostic way first (rules/peers/time-series/graph features), then optionally add GNN/temporal models behind the same interface.

**Indicator Contract (Doc 06) — required fields**

- Name, domain pack, target entity (provider/broker/beneficiary)
- Trigger logic (feature + threshold, graph pattern, temporal change)
- Explanation payload (reason codes + evidence pointers)
- Next-step guidance (what investigator does next)
- Monitoring metric(s) (precision-at-K, drift, complaint linkage, etc.)


### Stage 2 — Investigator validation loop (pre-go-live gate)

**Objective:** make investigators label outputs and explanation usefulness (not just “fraud/not fraud”).

**UI/UX screens**
3) *Case Queue / Triage Workbench* (ranked list; filter by indicator; SLA clock)
4) *Evidence Bundle Viewer* (raw events + timeline + links)
5) *Feedback Panel* (Agree/Disagree/Insufficient evidence + reason tags + next action)

**Feedback taxonomy (must-have fields)**

- Outcome: suspicious / not suspicious / insufficient evidence
- Reason tags: expected behavior / data quality / policy/program change / model/explanation issue
- Evidence adequacy: enough / missing X / contradictory
- Action taken: case opened / referred / closed / education / monitor


### Stage 3 — Operate in production (post-go-live)

**Objective:** monitor performance and decide changes with auditable governance; include pause/discontinue ability.

**UI/UX screens**
6) *Indicator Health Dashboard* (yield, adoption, precision proxy, drift alerts)
7) *Governance Change Log* (threshold/model changes, approvals, effective date)

This design directly supports the kind of lifecycle controls (testing/validation, performance monitoring, and discontinuation when needed) expected for serious federal AI use.

## 4) Evaluation gates + monitoring plan (required in v0.1)

### A. Evaluation gates (ship as “Definition of Done”)

**Gate 1 — Data readiness**

- Data provenance template completed (T05), including source systems, refresh cadence, PII/PHI handling, known gaps.

**Gate 2 — Indicator readiness**

- Each indicator has: evidence bundle definition, reason codes, and investigator next-step guidance.

**Gate 3 — Quality threshold**

- Minimum precision-at-K target for triage queue (set by PI Ops; recorded in T06).
- Explanation quality: investigators can answer “why flagged + what to check next” using the explanation rubric.

**Gate 4 — Safety \& governance**

- Risk screening completed (T03); if deemed high-impact, require independent review + discontinuation plan readiness consistent with M‑25‑21 expectations.


### B. Monitoring plan (what you measure, who reviews, and actions)

**Telemetry contract (monitoring/telemetry_contract.md)**

- Operational: volume flagged, queue aging, investigator actions, closure reasons
- Model/indicator: score distributions, drift checks, precision proxy from labels, false-positive hotspots
- Security/audit: access logs to sensitive evidence, changes to thresholds/models (change log)

**Weekly operating review (Template T08)**

- What changed? (data, policy, seasonality)
- What broke? (drift alerts, explanation complaints)
- What do we adjust? (thresholds, peer groups, evidence bundle)
- Do we pause/discontinue any indicator? (per discontinue_pause_policy.md)


## 5) Domain packs (v0.1 + your next expansions)

Each domain pack contains: schema, indicator library, and eval dataset spec.

### Domain pack 1 (v0.1 anchor): Medicare FFS (Chili Cook-Off)

**Scope:** Hospice, Part B, DME claims; detect anomalies/trends and translate to fraud indicators with explainability.[^26_1]

**Indicator examples (starter list of 10)**

- Peer-group outliers (utilization, unusual code mix)
- Temporal spikes (change-point vs baseline)
- Network anomalies (shared addresses/bank accounts; referral patterns)
- “Policy window” anomalies (pre/post known rule or edit changes)


### Domain pack 2 (next): Marketplace enrollment fraud (agent/broker)

**Schema highlights**

- Entities: consumer, enrollment, plan/issuer, broker (NPN), complaint/case, consent event, device/IP/contact points
- Edges: assisted_by, modified_by, associated_with, complaint_against, shared_device/contact

**Indicator examples (starter list of 10)**

- Broker-level abnormal switch rates vs peers (time-series)
- Many enrollments linked to same device/contact cluster (graph)
- Complaint-linked enrollments concentrated in narrow time windows (temporal)
- Consumer-broker association mismatches preceding changes (rules + explainability)

(Your UI/ops loop is essential here because investigators will distinguish “high-volume legitimate broker” from “malicious switch factory.”)

### Domain pack 3 (next): Medicaid dental/vision claims

**Schema highlights**

- Entities: beneficiary, rendering/billing provider, location, CDT/CPT/HCPCS codes, referring/ordering (if present), MCO/state segment
- Edges: treated, billed, performed_at, shared_address/phone/bank, temporal_sequence

**Indicator examples (starter list of 10)**

- Clinic rings: shared bank/address/contact across multiple NPIs (graph)
- Code-bundle communities deviating from peers (graph + peer outliers)
- High-frequency repeat services beyond clinical norms (temporal)
- Beneficiary–provider churn patterns (temporal + network)

***

### Where you start (first 10 working days)

1) Stand up the repo + templates (even empty) and run the 90-minute SME framing workshop; fill T01/T02 for 10–15 indicators.
2) Build the **Case Queue + Feedback UI** first (even with a simple scoring baseline), because that creates the human validation flywheel.
3) Implement 5 indicators end-to-end (with explanation payloads + evidence bundles) and run a “pre-go-live validation sprint” with investigators.
4) Add monitoring dashboard spec + weekly ops review cadence and require a change log for any threshold changes.

If you want, I can generate the actual **filled-in** templates for Marketplace agent/broker v0.1 (T01–T08) with example fields/values, plus a starter indicator list tailored to the data elements you said you have (complaint/casework + NPN).

<div align="center">⁂</div>

[^26_1]: https://www.thomsonreuters.com/en/reports/2026-ai-in-professional-services-report


---

# yes please

Below is a **filled v0.1 Accelerator draft** for the Marketplace agent/broker domain (with example values), designed so PI Ops + investigators frame indicators up front and continuously validate results in workflow.

## v0.1 package contents

This v0.1 assumes you have complaint/casework data and broker identifiers (NPN), and it operationalizes controls CMS has already used (e.g., blocking broker changes unless already associated; three‑way call exception) as both features and downstream actions.  It also includes lifecycle governance (documentation, data provenance, ongoing testing/validation, continuous monitoring, and a pause/discontinue plan), which aligns to OMB M‑25‑21 expectations for federal AI use.[^27_1]

## Repo layout (deliverable)

Use this as your initial repo; for v0.1 you can implement UI + templates fully, and keep “code-starters” minimal.

```text
marketplace-agent-broker-xai-accelerator-v0.1/
  README.md
  CHANGELOG.md
  /docs
    00_overview.md
    01_roles-and-raci.md
    02_domain-pack_marketplace.md
    03_indicator-contract.md
    04_ui-ux_workflow.md
    05_eval-gates.md
    06_monitoring-and-ops.md
    07_governance-change-control.md
  /templates
    T01_use-case-intake.md
    T02_indicator-builder.md
    T03_high-impact-ai-screening.md
    T04_model-card-xai.md
    T05_data-provenance.md
    T06_eval-plan-and-acceptance.md
    T07_go-live-checklist.md
    T08_weekly-ops-review.md
  /domain-pack_marketplace
    schema.md
    indicators_v0.1.md
    feature_dictionary.md
    eval_dataset_spec.md
  /ui
    screens_spec.md
    fields_dictionary.md
    api_contract.md (optional)
  /eval
    testset_spec.md
    scoring_rubric.md
    explanation_quality_rubric.md
  /monitoring
    telemetry_contract.md
    dashboards_spec.md
    drift_checks.md
    incident_runbook.md
    pause_discontinue_policy.md
  /code-starters
    /notebooks (optional)
      01_build_features.ipynb
      02_score_indicators.ipynb
      03_generate_explanations.ipynb
```


## Domain pack v0.1 (Marketplace)

**Workflow covered:** unauthorized enrollment / unauthorized plan switch detection + broker oversight + investigator prioritization.

**Entity model (minimal v0.1)**

- Entities: Consumer, Enrollment, Plan, Issuer, Agent/Broker (NPN), Complaint/Case, Enrollment Change Event, Consent/Call event (if available), Device/IP (if available).
- Key relationships:
    - Consumer —has→ Enrollment
    - Enrollment —has→ Change Event
    - Change Event —attributed_to→ Broker (NPN)
    - Complaint/Case —about→ Consumer/Enrollment; Complaint/Case —linked_to→ Broker (NPN) (directly or inferred)
    - Broker —associated_with→ Consumer/Enrollment (association flag/history) (important because CMS implemented association-based blocking as a control).

**Indicator contract (what every indicator must output)**

- Target entity: Broker NPN (primary), Consumer/Enrollment (secondary).
- Evidence bundle: timeline of change events, association status, linked complaints/cases, and supporting metadata.
- Explanation payload: reason codes + top 3 evidence pointers (so investigators can act quickly).


## UI/UX + workflow integration (SMEs + investigators)

v0.1 UI should be a thin layer over existing casework: it generates a prioritized queue, shows an evidence bundle, and captures investigator feedback with reason tags (data issue vs expected vs suspicious vs policy-driven). CMS explicitly runs complaint/casework pipelines for unauthorized plan switches/enrollments and has implemented system changes to prevent unauthorized broker actions, so your UI should connect directly to those workflows and controls.

**Minimum screens (v0.1)**

1) Use-case canvas (PI Ops)
2) Indicator builder (PI Ops + investigators)
3) Broker risk dashboard (Ops lead)
4) Case triage queue (Investigators)
5) Evidence bundle viewer (Investigators)
6) Feedback capture (Investigators)
7) Indicator health + change log (Ops lead / governance)

***

# Filled templates (Marketplace v0.1)

## T01 — Use-case intake (filled example)

```markdown
# T01 Use-Case Intake (Marketplace Agent/Broker Integrity) — v0.1

Use-case name:
- "Unauthorized Enrollment / Plan Switch Detection & Broker Oversight"

Decision being supported (not automated):
- "Which broker entities and enrollment-change events should be prioritized for investigation and consumer remediation?"

Primary users:
- Program Integrity Operations (queue owners)
- Investigators (case reviewers)

Primary target entities:
- Agent/Broker (NPN)
- Consumer enrollment-change event

Business problem statement:
- Detect and triage suspected unauthorized enrollments and unauthorized plan switches linked to agents/brokers, using complaint/case signals plus enrollment transaction patterns.

Known operational context / existing controls (to incorporate):
- System behavior: block broker changes unless broker already associated; three-way call exception path; these controls inform feature engineering and post-flag actions.

What constitutes harm (examples):
- Consumer enrolled without informed consent
- Consumer switched plans without consent
- Broker commission changes without consumer engagement
- Investigation backlog causes delayed remediation

Out of scope (v0.1):
- Final determinations of fraud/abuse
- Automated enforcement actions
- Automated consumer outreach

Data sources expected (v0.1):
- Complaint/casework system (unauthorized enrollment, unauthorized plan switch)
- Enrollment transaction history (adds/terminations/switches)
- Broker registry/identity (NPN)
- Broker-enrollment association history/flags
- Plan/issuer data

Success criteria (v0.1):
- Higher yield in top-K investigations (precision-at-K proxy via investigator labels)
- Reduced time-to-triage for high-risk brokers/events
- Transparent explanations investigators trust

Constraints:
- Human review required before any consequential action
- Auditability of evidence and changes to thresholds/models
```

Notes you can optionally attach for internal alignment: CMS reported large complaint volumes in 2024 for unauthorized plan switches/enrollments, and described the July 19, 2024 association-based blocking and three‑way call exception, plus substantial reductions in plan changes and commission changes afterward; you can use those as context and as “expected pattern changes” in your time-series modeling.

## T02 — Indicator builder (filled with 10 v0.1 indicators)

```markdown
# T02 Indicator Builder — Marketplace v0.1

Indicator 01: Broker abnormal switch rate spike (temporal + peer)
- Target entity: Broker (NPN)
- Description: Broker’s plan-switch rate rises sharply vs its own baseline and vs peer brokers in same state/region/channel.
- Data needed: enrollment changes, broker attribution, broker peer group attributes
- Suggested threshold (initial): z-score > 3 for 7-day rolling rate; confirm with SME
- Explanation reason codes: "Switch volume spike", "Peer outlier", "Abrupt change-point"
- Evidence bundle: timeline chart, peer comparison table, list of affected consumers
- Next action: investigator samples top 20 events; check association status + linked complaints

Indicator 02: Complaint-linked broker concentration
- Target entity: Broker (NPN)
- Description: Broker linked to unusually high number or rate of complaints for unauthorized enrollment/switch.
- Data needed: complaint/case, broker NPN linkage, time stamps
- Threshold: top 0.5% complaint rate (SME adjustable)
- Reason codes: "High complaint linkage", "Complaint severity mix"
- Evidence: complaint types, timestamps, resolution status, consumer count
- Next action: prioritize for case package + QA of consent evidence

Indicator 03: Association mismatch prior to enrollment change
- Target entity: Enrollment change event
- Description: Enrollment change attributed to broker not previously associated with that consumer/enrollment (or association added immediately before change).
- Data needed: broker-consumer association history, change events
- Threshold: any mismatch; score higher if repeated across many consumers
- Reason codes: "Not associated", "Association added just-in-time"
- Evidence: association audit trail + change event metadata
- Next action: check if change occurred via approved pathway; validate consumer engagement

Indicator 04: Rapid multi-consumer change burst ("spray and pray")
- Target entity: Broker (NPN)
- Description: Many consumers changed/enrolled in a tight time window inconsistent with broker’s normal pattern.
- Data needed: change timestamps, broker NPN
- Threshold: > X changes in Y minutes/hours, calibrated by SME
- Reason codes: "Burst activity", "Unusual time-of-day"
- Evidence: burst window list, affected consumers, geographic spread
- Next action: sample events, check device/channel consistency if available

Indicator 05: High reversal / remediation rate
- Target entity: Broker (NPN)
- Description: Large share of broker-driven changes are reversed or lead to remediation casework.
- Data needed: change events + subsequent reversals, complaint case outcomes
- Threshold: reversal rate > peer percentile
- Reason codes: "High reversal", "Remediation-heavy"
- Evidence: reversal timeline, complaint linkage
- Next action: deep-dive into affected populations; assess whether misconduct pattern exists

Indicator 06: Commission-change anomaly
- Target entity: Broker (NPN)
- Description: Unusual commission-related changes frequency (where available), especially when consumers later complain.
- Data needed: commission change events, complaint linkage
- Threshold: outlier vs peers
- Reason codes: "Commission anomaly", "Complaint overlap"
- Evidence: commission change history, consumer engagement evidence pointers
- Next action: prioritize for oversight; cross-check consent signals

Indicator 07: Consumer contact reuse cluster (graph)
- Target entity: Broker (NPN) and cluster
- Description: Many consumers linked by shared phone/email/address patterns, disproportionately tied to one broker or broker cluster.
- Data needed: consumer contact points, broker mapping
- Threshold: community size + density thresholds
- Reason codes: "Shared contact cluster", "Broker concentration"
- Evidence: small subgraph view (consumer nodes + shared contact node + broker)
- Next action: investigate whether legitimate assister patterns explain it

Indicator 08: Cross-broker handoff loop (graph + temporal)
- Target entity: Broker cluster
- Description: Consumers repeatedly shift between a small set of brokers over short intervals.
- Data needed: broker attribution history per consumer
- Threshold: > N broker switches within M days
- Reason codes: "Broker handoff loop", "Short-interval switches"
- Evidence: per-consumer broker timeline; cluster subgraph
- Next action: examine whether consumer initiated; check complaint overlap

Indicator 09: High-risk mix: spike + complaints + association mismatches
- Target: Broker (NPN)
- Description: Composite indicator combining 01 + 02 + 03 signals.
- Purpose: prioritization when investigator capacity is limited
- Reason codes: "Multi-signal corroboration"
- Evidence: top contributing indicators + pointers

Indicator 10: Policy-control evasion patterns (rules)
- Target: Enrollment change event
- Description: Events that appear to bypass normal consumer engagement patterns (channel anomalies, missing expected consent markers where available).
- Data needed: channel/source metadata, consent markers, call-center linkage
- Threshold: rule-based; SME-defined
- Reason codes: "Missing engagement marker", "Channel anomaly"
- Evidence: event metadata + consent evidence gaps
- Next action: route to specialized investigator queue
```


## T03 — High-impact AI screening (filled)

This template should mirror M‑25‑21’s framing that “high-impact AI” is when AI outputs are a principal basis for decisions/actions with legal/material effects, and that agencies need minimum risk management practices plus a discontinue plan if performance is inadequate.[^27_1]

```markdown
# T03 High-Impact AI Screening — Marketplace v0.1

AI output:
- Risk scores + ranked queues for broker and enrollment-change events
- Reason codes + evidence bundle pointers (explanations)

Is the AI output a principal basis for a consequential decision/action?
- No (v0.1 design intent): AI supports triage/prioritization only; investigators make decisions.

Could it materially affect rights/safety/benefits if misused?
- Yes, if used to auto-deny coverage changes, auto-sanction brokers, or auto-trigger consumer actions.

Controls (required):
- Role-based access; prohibit auto-enforcement actions
- Mandatory human review before any consequential action
- Explanations + evidence bundle always shown
- Change control + audit logs for thresholds/models
- Pause/discontinue mechanism if performance degrades

Independent review required before expanding scope?
- Yes: before any automation beyond triage/prioritization
```


## T04 — Model card (XAI) (filled)

M‑25‑21 encourages documenting capabilities/limitations and intended use, documenting data provenance, and conducting ongoing testing/validation with monitoring.[^27_1]

```markdown
# T04 Model Card / XAI Card — Marketplace v0.1

System name:
- Marketplace Agent/Broker Integrity XAI (Indicator-based)

Intended use:
- Support PI Ops and investigators by prioritizing broker/event review and surfacing explainable evidence bundles.

Not intended for:
- Automated enforcement or automated consumer impact actions
- Final determinations of fraud/abuse

Modeling approach (v0.1):
- Indicator scoring (rules + peer outliers + time-series change detection)
- Optional graph analytics features (community detection / ring signals)
- Explanations: reason codes + evidence pointers; (later) graph subgraph + temporal change narrative

Key limitations:
- Complaint data may be delayed/biased toward consumer awareness
- Attribution of changes to brokers may be incomplete in some channels
- Legitimate high-volume brokers may look anomalous without proper peer grouping

Human oversight:
- Investigator review required for any case action
- Feedback captured as labels + reason tags; used to tune thresholds and evaluate precision-at-K

Testing/validation plan:
- See T06 (pre-go-live acceptance + ongoing weekly monitoring)
```


## T05 — Data provenance (filled)

```markdown
# T05 Data Provenance — Marketplace v0.1

Dataset inventory (v0.1):
- Complaint/casework: complaint type, date received, resolution status, linked consumer/enrollment, linked broker NPN (if known)
- Enrollment transactions: enroll/switch/terminate events, timestamps, channel/source, plan/issuer
- Broker registry: NPN, status, org affiliation (if available)
- Broker-consumer association: association flag/history (where available)
- Optional: call-center/consent events; device/IP/contact points (if permitted and available)

Refresh cadence:
- Daily (ideal) for transactions and complaint intake; weekly acceptable for broker registry

Sensitive data handling:
- PII/PHI: store in client-controlled environment; apply RBAC; log access
- Data minimization: only fields required by indicators and evidence bundles

Known gaps (initial):
- Incomplete linkage between complaint and broker for some cases
- Missing consent markers in some channels
- Lag between event and complaint
```


## T06 — Evaluation plan + acceptance (filled)

This is your “go/no-go gate” plus the ongoing validation loop that M‑25‑21 expects through testing/validation and monitoring.[^27_1]

```markdown
# T06 Evaluation Plan & Acceptance — Marketplace v0.1

Evaluation goal:
- Ensure top-K queues are useful to investigators, and explanations are actionable.

Test set creation:
- Stratified sample of (a) high-risk, (b) medium-risk, (c) random cases
- Include known complaint-linked cases and non-complaint cases
- Preserve time order (avoid leakage)

Labels (investigator-driven):
- Outcome: suspicious / not suspicious / insufficient evidence
- Reason tags: expected behavior / data issue / policy-driven / model issue
- Evidence adequacy: enough / missing

Primary metrics:
- Precision@K for broker queue and event queue (K chosen by ops capacity)
- Investigator time-to-triage (baseline vs new)
- Explanation usefulness score (rubric)

Acceptance thresholds (v0.1 initial targets):
- Precision@K meets SME-defined minimum for pilot deployment
- Explanation usefulness: >= 80% cases rated "actionable"
- No critical safety violations (e.g., missing evidence bundle for high-score cases)

Sign-off:
- PI Ops lead + investigator lead approve go-live
```


## T07 — Go-live checklist (filled)

```markdown
# T07 Go-Live Checklist — Marketplace v0.1

Security / access
- RBAC configured for PI Ops and investigators
- Audit logging enabled for evidence access and threshold changes

Data readiness
- Data sources connected and refresh working
- Data provenance (T05) completed

Indicator readiness
- Each indicator has reason codes + evidence bundle definition
- Investigator next steps documented
- Known limitations listed

Evaluation gates
- T06 acceptance criteria met
- Baseline metrics captured

Operations
- Monitoring dashboard live (indicator health, drift checks)
- Weekly ops review scheduled (T08)
- Pause/discontinue mechanism tested
```


## T08 — Weekly ops review (filled)

This is where you operationalize continuous monitoring and discontinuation readiness (a core M‑25‑21 theme).[^27_1]

```markdown
# T08 Weekly Ops Review — Marketplace v0.1

Week of:
Attendees:
- PI Ops lead, investigator lead, data/ML lead

1) Volume & workflow
- # brokers flagged, # events flagged
- Queue aging, investigator throughput

2) Quality signals
- Precision@K proxy (from investigator labels)
- Top false-positive drivers (reason tags)
- Explanation usefulness complaints

3) Drift & anomalies
- Indicator score distribution drift
- Complaint intake drift (volume/lag)
- Peer group shifts (seasonality/policy)

4) Changes proposed (must log)
- Threshold adjustments
- Peer group definitions
- Evidence bundle requirements
- Any indicator pause/discontinue decision

5) Decisions & owners
- Approved changes + effective date
- Retraining/recalibration plan (if applicable)
```


***

## What I’d do next (to make this real in 10 working days)

1) Run the **SME framing workshop** (PI Ops + investigators) and finalize the 10 indicators above into your `domain-pack_marketplace/indicators_v0.1.md`.
2) Build the **Case Queue + Evidence Bundle + Feedback capture** screens first; even a spreadsheet-backed UI is acceptable for v0.1 if it enforces the workflow and logs decisions.
3) Implement only Indicators 01–05 end-to-end first (time-series + complaint linkage + association mismatch) because CMS-described controls and complaint pipelines make these immediately meaningful.

If you want, I can also draft `ui/screens_spec.md` and `ui/fields_dictionary.md` (exact fields + validation rules) so you can hand it to a dev and get a working v0.1 UI quickly.

<div align="center">⁂</div>

[^27_1]: https://www.thomsonreuters.com/en/reports/2026-ai-in-professional-services-report


---

# Just to clarify. I want to build the accelerator that can handle multiple use cases, starting with Medicare FFS claims, marketplace enrollment agent/broker, and Medicaid dental and vision claims. How should I differentiate the common elements, and use case specific info. Provide me the first draft of the accelerator package.

You should design the accelerator as a **core platform kit** (common elements) plus **domain packs** (use-case specific schemas, features, indicators, and evaluation sets). This matches the Chili Cook-Off’s intent: reusable, scalable tech that reduces labor while keeping humans in the loop, starting from Medicare FFS anomalies and expanding to other program-integrity domains.  It also aligns with OMB M‑25‑21’s emphasis on AI lifecycle infrastructure (development, testing, deployment, continuous monitoring), documentation, and ongoing testing/validation with the ability to discontinue when performance isn’t appropriate.[^28_1]

## 1) How to split common vs use-case specific

Common elements (“Core Kit”) — reusable across all domains

- **Governance \& human-in-loop workflow:** SME framing templates, investigator review loop, change control, audit log requirements, pause/discontinue policy.[^28_1]
- **Indicator contract:** standardized definition of an “indicator” output (risk entity, reason codes, evidence bundle pointers, next steps, monitoring metrics).
- **Explainability framework:** local (feature), network (subgraph), temporal (change narrative) explanation payload format.
- **Evaluation harness:** test set format, scoring rubric (precision@K, stability, explanation usefulness), acceptance gates.[^28_1]
- **Monitoring/LLMOps/MLOps:** telemetry contract, drift checks, weekly ops review cadence, incident runbook, discontinue triggers.[^28_1]
- **Reference architectures:** generic “secure deployment patterns” for AWS + Azure with plug points for domain data sources and compute.[^28_1]
- **UI/UX shells:** common screens (use-case canvas, indicator builder, triage queue, evidence viewer, feedback capture, indicator health dashboard).

Use-case specific elements (“Domain Packs”) — one per domain

- **Entity/edge schema:** claims vs enrollment have different entities, event types, and evidence bundles.
- **Feature dictionary:** domain-specific derived features (e.g., procedure code patterns vs broker association mismatches).
- **Indicator library:** the initial set of indicators + thresholds + reason codes + next steps tuned to domain workflows.
- **Evaluation dataset spec:** sampling strategy and label guidance tailored to domain reality.
- **Policy/ops integration:** downstream actions differ (e.g., Medicare claim review vs Marketplace remediation vs Medicaid MFCU referral).


## 2) First draft: Accelerator v0.1 package

Below is a “ready-to-hand-to-a-team” draft. You can paste this into a repo today and fill iteratively.

### A) Repo structure

```text
xai-program-integrity-accelerator/
  README.md
  CHANGELOG.md
  /core
    /docs
      00_overview.md
      01_roles-raci.md
      02_delivery-playbook.md
      03_indicator-contract.md
      04_explainability-spec.md
      05_eval-harness.md
      06_monitoring-ops.md
      07_governance-change-control.md
      08_security-privacy.md
      09_reference-architecture_azure.md
      10_reference-architecture_aws.md
      11_ui-ux_spec.md
    /templates
      C01_use-case-canvas.md
      C02_indicator-builder.md
      C03_high-impact-ai-screen.md
      C04_model-card-xai.md
      C05_data-provenance.md
      C06_eval-plan-acceptance.md
      C07_go-live-checklist.md
      C08_weekly-ops-review.md
      C09_change-request.md
    /eval
      testset_format.csv (spec)
      scoring_rubric.md
      explanation_quality_rubric.md
    /monitoring
      telemetry_contract.md
      dashboards_spec.md
      drift_checks.md
      incident_runbook.md
      pause_discontinue_policy.md
    /ui
      screens_spec.md
      fields_dictionary.md
      api_contract.md (optional)
  /domain-packs
    /medicare_ffs_claims
      README.md
      schema.md
      feature_dictionary.md
      indicators_v0.1.md
      eval_dataset_spec.md
      evidence_bundle_spec.md
    /marketplace_agent_broker_enrollment
      README.md
      schema.md
      feature_dictionary.md
      indicators_v0.1.md
      eval_dataset_spec.md
      evidence_bundle_spec.md
    /medicaid_dental_vision_claims
      README.md
      schema.md
      feature_dictionary.md
      indicators_v0.1.md
      eval_dataset_spec.md
      evidence_bundle_spec.md
  /code-starters
    /notebooks
      01_build_features.ipynb
      02_score_indicators.ipynb
      03_generate_explanations.ipynb
    /pipelines
      pipeline_skeleton.md
    /iac
      terraform_skeleton.md
```


### B) Core Kit (first-draft content)

**core/docs/00_overview.md (draft)**

- Mission: “detect anomalies/trends, translate into novel indicators, reduce labor, keep humans meaningfully in loop” (lifted from Chili Cook-Off framing).
- Supported domains (v0.1): Medicare FFS claims; Marketplace agent/broker enrollment; Medicaid dental/vision claims.
- Non-goals: automated enforcement, automated denial/termination, final fraud determinations.

**core/docs/03_indicator-contract.md (draft)**

- Output fields (required):
    - `indicator_id`, `domain_pack`, `target_entity_type`, `target_entity_id`
    - `score` (0–100), `priority_band`, `confidence_band`
    - `reason_codes[]` (human-readable)
    - `evidence_bundle_refs[]` (links/IDs to raw events)
    - `explanations` object: `local`, `network`, `temporal`
    - `recommended_next_steps[]`
    - `monitoring_metrics[]` (which dashboards measure it)

**core/docs/05_eval-harness.md (draft)**

- Primary metric: precision@K (because queues are capacity-limited).
- Secondary: explanation usefulness (investigator-rated), stability/drift, time-to-triage improvement.
- Acceptance gates: Data readiness → Indicator readiness → Quality threshold → Safety/Governance signoff (reflecting ongoing testing/validation expectations in M‑25‑21).[^28_1]

**core/monitoring/pause_discontinue_policy.md (draft)**

- Trigger examples: precision proxy drops below threshold for 2 consecutive weeks; drift alert sustained; investigator “not actionable” ratings exceed X%; critical data provenance issue found.
- Action: pause indicator → investigate → fix → revalidate → re-enable; for high-impact usage expansions, require independent review and risk acceptance consistent with M‑25‑21 governance language.[^28_1]

**core/ui/screens_spec.md (draft)**
Common screens:

1) Use-case canvas (SME framing)
2) Indicator builder (SME hypotheses)
3) Triage queue (investigators)
4) Evidence bundle viewer
5) Feedback capture (labels + reason tags)
6) Indicator health dashboard
7) Change log \& approvals

### C) Domain Pack 1: Medicare FFS claims (Chili Cook-Off anchor)

Justification: Phase 2 provided Medicare FFS Hospice, Part B, and DME claims data via CMS LDS; the goal was explainable AI to detect anomalies/trends and propose scalable analytic/policy solutions.

**domain-packs/medicare_ffs_claims/indicators_v0.1.md (starter set)**

- Peer outlier indicators (per provider, per beneficiary segment)
- Temporal change-point indicators (per provider, per code family)
- Network/ring indicators (shared address/phone/bank; referral patterns if available)
- “Evidence bundle”: claim lines, code distributions, peer group stats, linked entities.


### D) Domain Pack 2: Marketplace agent/broker enrollment integrity

You said you have complaints/casework and broker IDs (NPN), so v0.1 can be strong quickly.

**schema.md (minimum)**

- Entities: consumer, enrollment, plan/issuer, broker (NPN), change event, complaint/case, association history.

**indicators_v0.1.md (use the 10 we drafted earlier)**

- Switch rate spike; complaint-linked concentration; association mismatch; burst changes; reversal/remediation rate; commission anomaly (if available); shared contact clusters; cross-broker handoff loops; composite risk; consent/engagement marker gaps.


### E) Domain Pack 3: Medicaid dental/vision claims

**schema.md (minimum)**

- Entities: beneficiary, rendering/billing provider, location, CDT/CPT/HCPCS, date-of-service, MCO/state segment.

**indicators_v0.1.md (starter set of 10)**

- Clinic ring (shared address/phone/bank across NPIs)
- Procedure bundle community outlier
- Temporal over-utilization spikes vs peers
- Unusual provider-beneficiary churn
- Location/time anomalies (e.g., improbable volumes)
- Peer outliers by age group or eligibility segment


## 3) Where to start (the build sequence)

1) Implement the **Core UI + feedback loop** first (triage queue + evidence bundle + feedback capture).
2) Implement **one thin slice** per domain (3–5 indicators each) before adding advanced modeling.
3) Only after feedback is flowing, add KG/GNN/time-series models behind the indicator contract—this keeps the accelerator deployable across client constraints while still enabling sophistication.

If you want, I can generate the actual contents of the following files next (as copy/paste Markdown), so you have a “real repo” text you can drop into Git:

- `core/docs/02_delivery-playbook.md` (2-week implementation plan + RACI)
- `core/templates/C01–C09` fully populated with example fields/values
- Each domain pack’s `schema.md`, `evidence_bundle_spec.md`, and a 10-indicator library (complete with reason codes and next steps)

Which one do you want me to generate first: the **Core Kit templates** (C01–C09) or the **three domain pack schemas**?

<div align="center">⁂</div>

[^28_1]: https://www.thomsonreuters.com/en/reports/2026-ai-in-professional-services-report


---

# the core kit templates.

Below are the **Core Kit Templates (C01–C09)** as copy/paste Markdown you can drop into your repo under `/core/templates/`. They’re written to work across your three starting domain packs (Medicare FFS claims, Marketplace agent/broker enrollment, Medicaid dental/vision claims) and to enforce human-in-loop governance, ongoing testing/validation, continuous monitoring, and a pause/discontinue mechanism consistent with OMB M‑25‑21.

***

## C01_use-case-canvas.md

```markdown
# C01 Use-Case Canvas (Core) — v0.1

## 1) Basic metadata
- Use-case name:
- Domain pack: (medicare_ffs_claims | marketplace_agent_broker_enrollment | medicaid_dental_vision_claims | other)
- Version:
- Date:
- Owner (Ops):
- Owner (Analytics/ML):
- Owner (Product/Accelerator):

## 2) Decision support (not automation)
- Decision being supported (one sentence):
- What human action happens next (queue, case creation, referral, outreach, edit recommendation):
- What decisions/actions are explicitly out of scope for AI automation in v0.1:

## 3) Users and workflow
- Primary users: (PI Ops | investigators | SIU | auditors | clinicians | other)
- Workflow integration point(s): (existing case tool, ticketing system, analytics portal, etc.)
- Expected cadence: (daily triage | weekly review | ad hoc)

## 4) Target entities
- Primary risk entity: (provider | broker | beneficiary | clinic/group | enrollment event | claim event | other)
- Secondary entities:

## 5) Problem framing (SME input)
- SME hypotheses (3–7 bullets):
- What “suspicious” looks like (examples):
- What “expected but unusual” looks like (examples):
- Known seasonal/policy artifacts to control for:

## 6) Harm / sensitivity / guardrails
- Potential harms if false positives:
- Potential harms if false negatives:
- Populations with elevated sensitivity (equity, vulnerable groups):
- Guardrails (human review requirements, access controls, minimum evidence):

## 7) Data requirements (summary)
- Data sources:
- Key identifiers / link keys:
- Minimum history required:
- Refresh cadence:
- Known gaps / biases:

## 8) Success criteria (pilot → production)
- Primary metric(s): (precision@K, yield per hour, time-to-triage, dollars-at-risk surfaced, etc.)
- Secondary metric(s): (stability, investigator satisfaction, explanation usefulness)
- “Definition of done” for go-live (3–5 bullets):
```


***

## C02_indicator-builder.md

```markdown
# C02 Indicator Builder (Core) — v0.1

Create one entry per indicator.

## Indicator metadata
- Indicator ID:
- Indicator name:
- Domain pack:
- Target entity type:
- Target entity grain: (NPI | NPN | beneficiary ID | claim ID | enrollment change ID | location | group ID)
- Owner (SME):
- Owner (Analytics):

## Natural language definition (SME-first)
- What it flags (1–2 sentences):
- What it does NOT mean (avoid misuse):
- Why it matters (harm/prevention value):

## Detection logic (v0.1)
Choose one or more:
- Type: (rule | peer outlier | time-series change | graph pattern | hybrid)
- Feature inputs (list):
- Baseline / peer group definition:
- Threshold(s) and rationale:
- Volume expectations (how many per week is “normal”):
- Failure modes / confounders (SME-known):

## Evidence bundle (must-have)
- Required evidence elements:
- Evidence pointers (tables/fields/events):
- Minimum evidence completeness rule (e.g., must show last 90 days):

## Explanation payload (must-have)
- Reason codes (3–10, human readable):
- Local explanation (top features):
- Temporal explanation (what changed, window):
- Network explanation (if graph used): (subgraph summary requirements)

## Recommended next steps (workflow)
- Suggested investigator actions:
- Routing: (queue name, priority, SLA)
- “Stop conditions” (when to close as non-suspicious):

## Monitoring plan (per indicator)
- Health metrics: (drift, volume, precision proxy)
- Alert thresholds:
- Review cadence:
- Owner for ongoing review:

## Release controls
- Status: (draft | piloting | approved | paused | retired)
- Date approved:
- Approver(s):
- Notes / links:
```


***

## C03_high-impact-ai-screen.md

```markdown
# C03 High-Impact AI Screening (Core) — v0.1

Purpose: determine whether this AI use case is "high-impact" and what additional controls apply.
(Record the rationale; revisit when scope changes.)

## 1) AI output and usage
- AI outputs: (ranked queue, risk score, explanation, recommendation)
- How outputs are used today:
- Who consumes outputs:

## 2) Consequential impact assessment
Does the AI output serve as a principal basis for a decision/action that has legal, material, binding,
or significant effect on rights or safety?
- Yes / No / Not yet (triage-only)

If "Yes" or "Potentially":
- Describe the decision/action:
- Potential impact(s) on individuals/entities:
- Appeal/review process (if any):

## 3) Controls (minimum set)
Required controls for any sensitive use:
- Human review required before consequential action
- Evidence bundle visibility
- Access controls + audit logging
- Change control for thresholds/models
- Monitoring + drift checks
- Pause/discontinue mechanism

## 4) Independent review requirement
- Does this use case require independent review before risk acceptance?
  - Yes / No
- Reviewer role(s):

## 5) Discontinue plan readiness
- Define conditions that require pause/discontinue:
- Who has authority to pause:
- Who approves re-enable:

## 6) Determination and sign-off
- Determination: (high-impact | not high-impact | triage-only)
- Rationale:
- Signed by:
- Date:
```

This template operationalizes M‑25‑21’s emphasis on minimum risk management for high-impact AI and having a plan to discontinue use when performance is not appropriate.

***

## C04_model-card-xai.md

```markdown
# C04 Model Card / XAI Card (Core) — v0.1

## System identity
- System name:
- Version:
- Domain pack(s):
- Owner:

## Intended use
- Intended use (what decisions it supports):
- Out-of-scope use (explicitly forbidden):
- Human oversight requirements:

## Data
- Data sources used (training/testing/operation):
- Data refresh cadence:
- Key limitations/biases:
- Data provenance reference: (link to C05)

## Modeling approach (v0.1)
- Indicator scoring approach:
- Optional models used: (graph learning, anomaly detection, etc.)
- Feature families:
- How peer groups are constructed:

## Explainability
- Local explanation method:
- Network explanation method:
- Temporal explanation method:
- Reason code library location:

## Performance (pilot)
- Primary metrics:
- Results summary:
- Failure modes observed:
- “Known limitations” users must understand:

## Monitoring and validation
- Ongoing testing/validation plan (link to C06 + monitoring docs):
- Drift checks:
- Recalibration triggers:
- Pause/discontinue policy reference:

## Change history
- Major changes in this version:
```

This corresponds to M‑25‑21’s recommendations on documenting capabilities/limitations, documenting provenance, and conducting ongoing testing/validation with monitoring.

***

## C05_data-provenance.md

```markdown
# C05 Data Provenance & Traceability (Core) — v0.1

## 1) Data inventory (by domain pack)
For each dataset:
- Dataset name:
- Source system / owner:
- Access method:
- Refresh cadence:
- Fields used (high-level):
- Key identifiers / link keys:
- Retention policy:
- Sensitivity classification: (PII/PHI/other sensitive)
- Known gaps/biases:
- Quality checks performed:

## 2) Feature traceability
- Feature store / feature table location:
- For each major feature family, list source tables and logic references.

## 3) Label provenance (if applicable)
- Who labels:
- Label definitions:
- Label storage and access:
- Risk of label leakage:

## 4) Auditability
- How to reproduce a score/explanation for a specific case (steps/links):
- Logs required to support audit:

## 5) Legal / privacy / security constraints
- Restrictions on data sharing:
- Restrictions on external model training:
- Cross-agency/cross-program reuse constraints:
```

M‑25‑21 highlights the importance of data traceability and provenance documentation for AI use and procurement.

***

## C06_eval-plan-acceptance.md

```markdown
# C06 Evaluation Plan & Acceptance Criteria (Core) — v0.1

## 1) Evaluation scope
- Domain pack:
- Indicators in scope:
- Environment: (dev/test/prod-like)
- Intended use: (triage-only vs consequential)

## 2) Test set design (must prevent leakage)
- Time window(s):
- Sampling strategy: (stratified by score, random, complaint-linked, etc.)
- Sample size targets:
- Exclusions:

## 3) Labeling plan (human-in-loop)
- Labelers: (investigators/SMEs)
- Labels captured:
  - outcome: (suspicious | not suspicious | insufficient evidence)
  - reason tags: (expected behavior | data quality | policy-driven | model issue | other)
  - explanation usefulness: (actionable | not actionable | unclear)
- Inter-rater agreement plan (lightweight):

## 4) Metrics
Primary:
- Precision@K (K based on investigator capacity)
- Yield per hour (cases leading to meaningful action)

Secondary:
- Queue aging reduction / time-to-triage
- Stability over time (variance of top-K composition)
- Explanation usefulness rate
- Safety metrics (e.g., missing evidence bundle rate)

## 5) Acceptance thresholds (v0.1)
- Minimum precision@K:
- Minimum explanation usefulness rate:
- Maximum critical error rate:
- Drift tolerances:

## 6) Sign-offs and gates
Gate 1: Data readiness complete (C05 approved)
Gate 2: Indicator contract complete for each indicator (C02 approved)
Gate 3: Evaluation thresholds met
Gate 4: High-impact screening completed (C03)
Gate 5: Go-live checklist complete (C07)

Approvers:
- PI Ops lead:
- Investigator lead:
- Security/privacy:
- Product/accelerator owner:
```

This implements the ongoing testing/validation expectations emphasized in M‑25‑21 (including testing in real-world conditions and post-award monitoring/evaluation concepts).

***

## C07_go-live-checklist.md

```markdown
# C07 Go-Live Checklist (Core) — v0.1

## Security & access
- RBAC configured for roles
- Audit logging enabled (access + changes)
- Data sensitivity handling confirmed

## Data readiness
- Data provenance (C05) completed and approved
- Data quality checks passing
- Refresh cadence operating

## Indicator readiness
- C02 completed for each indicator
- Evidence bundle spec complete per domain pack
- Reason codes validated by investigators
- Next-step actions and routing configured

## Evaluation gate
- C06 thresholds met and signed off
- “Known limitations” communicated to users

## Monitoring & ops
- Telemetry contract implemented
- Dashboards live (indicator health, drift, ops throughput)
- Weekly ops review scheduled (C08)
- Incident runbook ready
- Pause/discontinue controls tested (even if manual in v0.1)

## Governance
- Change request process live (C09)
- High-impact screening complete (C03)
- Model card completed (C04)

Go-live decision:
- Approved / Not approved
- Conditions:
- Date:
- Signatures:
```


***

## C08_weekly-ops-review.md

```markdown
# C08 Weekly Ops Review (Core) — v0.1

## Meeting metadata
- Week of:
- Domain pack(s) reviewed:
- Attendees (Ops, investigators, analytics, security/privacy as needed):

## 1) Operations
- # cases generated (by indicator)
- # cases reviewed
- Queue aging / SLA adherence
- Investigator throughput

## 2) Quality (from human feedback)
- Precision@K proxy:
- Top false positives (reason tags)
- Top false negatives (if discovered)
- Explanation usefulness (% actionable)

## 3) Drift & data changes
- Data refresh issues:
- Score distribution drift:
- Peer group shifts:
- Policy/seasonality notes:

## 4) Decisions
- Threshold changes requested:
- Indicators to pause/discontinue:
- Indicators to promote from pilot → approved:
- Retraining/recalibration actions:

## 5) Action items
- Owner / due date / link to C09 change request:
```

This supports continuous monitoring and operational governance emphasized in M‑25‑21.

***

## C09_change-request.md

```markdown
# C09 Change Request (Core) — v0.1

Change ID:
Date:
Requested by:
Domain pack:
Type: (threshold change | peer group change | new indicator | model change | data change | UI change)

## 1) What is changing?
- Current behavior:
- Proposed behavior:
- Files/indicators impacted:

## 2) Why change?
- Evidence (metrics, investigator feedback, drift alerts):
- Risk of not changing:

## 3) Risk assessment
- Could this increase harm/impact?
- Does it change high-impact determination (C03)?
- Security/privacy considerations:

## 4) Validation plan
- What tests will be run?
- Success criteria:
- Rollback plan:

## 5) Approvals
- PI Ops:
- Investigator lead:
- Analytics lead:
- Security/privacy:
- Product/accelerator owner:

## 6) Release notes
- Effective date:
- Communication plan:
- Link to updated model card (C04) and eval plan (C06):
```


***

## What you do next (to make v0.1 real)

1) Copy these templates into your repo under `/core/templates`.
2) Run one SME framing workshop per domain pack and fill **C01 + 5–10 C02s** per domain.
3) Build the UI flow that enforces **C02 → triage → feedback → C08 → C09**, because that loop is what differentiates a “demo” from a productionizable accelerator.

If you want, I can next generate the **Core UI field dictionary** (`/core/ui/fields_dictionary.md`) so your dev team can implement the screens consistently across the three domain packs.

---

# yes please

Below is a first-draft **`/core/ui/fields_dictionary.md`** you can paste into your repo. It’s designed to support all three domain packs (Medicare FFS claims, Marketplace agent/broker, Medicaid dental/vision) while enforcing the human-in-loop workflow, auditability, and ongoing monitoring/validation that OMB M‑25‑21 emphasizes for federal AI use (including measuring/monitoring performance and having a discontinue plan when performance is not appropriate).

***

## core/ui/fields_dictionary.md

```markdown
# Core UI Fields Dictionary — v0.1
Applies to the Program Integrity XAI Accelerator Core UI across domain packs.

Conventions
- Types: string | int | float | bool | enum | date | datetime | array<T> | object
- IDs: should be stable, non-PII tokens whenever possible.
- Audit: any change to config/thresholds requires change_log_id and user_id.

------------------------------------------------------------
A) Global / shared fields
------------------------------------------------------------

field: tenant_id
type: string
required: yes
description: Client environment identifier.

field: domain_pack_id
type: enum
required: yes
allowed: ["medicare_ffs_claims", "marketplace_agent_broker_enrollment", "medicaid_dental_vision_claims", "other"]
description: Determines schema, indicators, evidence bundle mappings.

field: use_case_id
type: string
required: yes
description: Unique ID for a configured use-case instance (links to C01).

field: use_case_version
type: string
required: yes
description: Semver (e.g., "0.1.0").

field: indicator_id
type: string
required: yes (for indicator-related screens)
description: Unique ID for an indicator (links to C02).

field: indicator_version
type: string
required: yes
description: Semver or dated version.

field: created_at
type: datetime
required: yes

field: created_by_user_id
type: string
required: yes

field: last_modified_at
type: datetime
required: yes

field: last_modified_by_user_id
type: string
required: yes

field: user_role
type: enum
required: yes
allowed: ["pi_ops", "investigator", "analytics", "security_privacy", "admin", "viewer"]
description: Controls permissions and what actions are enabled.

field: audit_event_id
type: string
required: auto-generated
description: Immutable ID for an audit event record.

------------------------------------------------------------
B) Use-case Canvas (Screen: UC01)
------------------------------------------------------------

field: use_case_name
type: string
required: yes

field: decision_supported
type: string
required: yes
description: "Decision being supported (not automated)."

field: downstream_action_type
type: enum
required: yes
allowed: ["triage_queue", "case_create", "referral", "audit_targeting", "edit_recommendation", "other"]
description: What happens next in workflow.

field: out_of_scope_actions
type: array<string>
required: yes
description: Explicitly forbidden automation (e.g., "auto-sanction", "auto-deny").

field: primary_users
type: array<enum>
required: yes
allowed: ["pi_ops", "investigator", "siu", "auditor", "other"]

field: primary_entity_type
type: enum
required: yes
allowed: ["provider", "broker", "beneficiary", "clinic_group", "claim", "enrollment_event", "other"]

field: smes_involved
type: array<object>
required: yes
object fields:
  - sme_role: enum ["pi_ops", "investigator", "clinical", "policy", "legal", "privacy", "security", "other"]
  - sme_name_or_alias: string (avoid full PII if possible)
  - org_unit: string
  - contact: string (optional)

field: harm_statement_fp
type: string
required: yes
description: Potential harm from false positives.

field: harm_statement_fn
type: string
required: yes
description: Potential harm from false negatives.

field: guardrails
type: array<string>
required: yes
description: Mandatory human review, minimum evidence, etc.

field: known_confounders
type: array<string>
required: no
description: Seasonality, policy changes, operational changes.

------------------------------------------------------------
C) Indicator Builder (Screen: IND01)
------------------------------------------------------------

field: indicator_name
type: string
required: yes

field: indicator_description
type: string
required: yes
description: SME-first language.

field: indicator_type
type: array<enum>
required: yes
allowed: ["rule", "peer_outlier", "time_series", "graph_pattern", "hybrid"]

field: target_entity_type
type: enum
required: yes
allowed: ["provider", "broker", "beneficiary", "clinic_group", "claim", "enrollment_event", "other"]

field: target_entity_grain
type: string
required: yes
description: Examples: NPI, NPN, claim_id, enrollment_change_id.

field: feature_inputs
type: array<string>
required: yes
description: Feature names; domain pack must map them.

field: peer_group_definition
type: string
required: no
description: Human-readable; required if indicator_type includes peer_outlier.

field: scoring_method
type: enum
required: yes
allowed: ["rules_only", "rules_plus_stats", "model_score", "hybrid_score"]
description: v0.1 can start with rules/stats.

field: threshold_config
type: object
required: yes
object fields:
  - threshold_type: enum ["static", "percentile", "zscore", "change_point", "composite"]
  - threshold_value: string (store as string to allow expressions, e.g., "p99", "z>3")
  - threshold_window_days: int (optional)
  - threshold_notes: string

field: expected_volume_per_week
type: object
required: no
object fields:
  - min: int
  - max: int
  - notes: string

field: reason_code_library
type: array<object>
required: yes
object fields:
  - reason_code: string (short stable token, e.g., "SWITCH_SPIKE")
  - display_text: string (human-friendly)
  - evidence_pointer: string (what evidence supports it)

field: evidence_bundle_requirements
type: array<string>
required: yes
description: Minimum evidence elements to show in UI.

field: next_steps
type: array<string>
required: yes
description: Investigator actions.

field: routing
type: object
required: yes
object fields:
  - queue_name: string
  - priority_band: enum ["P0", "P1", "P2", "P3"]
  - sla_hours: int

field: monitoring_metrics
type: array<enum>
required: yes
allowed: ["volume", "precision_proxy", "drift", "explanation_usefulness", "queue_aging", "latency", "other"]

field: indicator_status
type: enum
required: yes
allowed: ["draft", "pilot", "approved", "paused", "retired"]

field: approval
type: object
required: no (required for approved)
object fields:
  - approved_by_user_id: string
  - approved_at: datetime
  - approval_notes: string

------------------------------------------------------------
D) Broker/Provider Risk Dashboard (Screen: DASH01)
(Works for any primary_entity_type)
------------------------------------------------------------

field: entity_id
type: string
required: yes

field: entity_type
type: enum
required: yes
allowed: ["provider", "broker", "beneficiary", "clinic_group", "other"]

field: entity_display_name
type: string
required: no

field: risk_score
type: float
required: yes
range: 0-100

field: confidence_band
type: enum
required: yes
allowed: ["low", "medium", "high"]

field: priority_band
type: enum
required: yes
allowed: ["P0", "P1", "P2", "P3"]

field: top_reason_codes
type: array<string>
required: yes
description: List of reason_code tokens.

field: time_window_start
type: date
required: yes

field: time_window_end
type: date
required: yes

field: indicator_contributions
type: array<object>
required: no
object fields:
  - indicator_id: string
  - indicator_score_component: float
  - evidence_count: int

------------------------------------------------------------
E) Case Triage Queue (Screen: CASE01)
------------------------------------------------------------

field: case_id
type: string
required: yes
description: Accelerator-generated case or link to external casework tool.

field: case_source
type: enum
required: yes
allowed: ["accelerator", "external_case_system"]

field: external_case_ref
type: string
required: no
description: Link/ID in agency case management system.

field: case_status
type: enum
required: yes
allowed: ["new", "in_review", "needs_more_info", "closed", "referred", "escalated"]

field: triggering_indicator_ids
type: array<string>
required: yes

field: triggering_entity
type: object
required: yes
object fields:
  - entity_type: enum ["provider", "broker", "beneficiary", "clinic_group", "claim", "enrollment_event", "other"]
  - entity_id: string

field: recommended_queue
type: string
required: yes

field: assigned_to_user_id
type: string
required: no

field: assigned_at
type: datetime
required: no

field: due_at
type: datetime
required: no
description: SLA deadline.

------------------------------------------------------------
F) Evidence Bundle Viewer (Screen: EVID01)
------------------------------------------------------------

field: evidence_bundle_id
type: string
required: yes

field: evidence_items
type: array<object>
required: yes
object fields:
  - evidence_type: enum ["event", "transaction", "claim_line", "complaint", "association_record", "profile", "document", "other"]
  - source_table_or_system: string
  - source_record_id: string
  - event_datetime: datetime (optional)
  - summary: string
  - sensitive_flag: bool

field: timeline_items
type: array<object>
required: no
object fields:
  - t: datetime
  - label: string
  - linked_evidence_item_ids: array<string>

field: network_subgraph
type: object
required: no
description: Small subgraph used for explanation (nodes + edges).
object fields:
  - nodes: array<object> (node_id, node_type, display_label)
  - edges: array<object> (src_id, dst_id, edge_type, strength)

field: temporal_context
type: object
required: no
object fields:
  - baseline_window_days: int
  - comparison_window_days: int
  - detected_change_point_at: datetime (optional)
  - narrative: string

------------------------------------------------------------
G) Investigator Feedback (Screen: FB01)
------------------------------------------------------------

field: feedback_id
type: string
required: yes

field: feedback_outcome
type: enum
required: yes
allowed: ["suspicious", "not_suspicious", "insufficient_evidence"]

field: feedback_reason_tags
type: array<enum>
required: yes
allowed: ["expected_behavior", "data_quality_issue", "policy_program_change", "model_issue", "explanation_issue", "needs_more_info", "other"]

field: explanation_usefulness
type: enum
required: yes
allowed: ["actionable", "not_actionable", "unclear"]

field: evidence_adequacy
type: enum
required: yes
allowed: ["enough", "missing", "contradictory"]

field: missing_evidence_notes
type: string
required: no

field: recommended_next_action
type: enum
required: yes
allowed: ["open_case", "close_case", "refer", "educate", "monitor", "request_more_info"]

field: investigator_notes
type: string
required: no

field: feedback_timestamp
type: datetime
required: yes

------------------------------------------------------------
H) Indicator Health & Monitoring (Screen: MON01)
------------------------------------------------------------

field: indicator_health_id
type: string
required: yes

field: health_period_start
type: date
required: yes

field: health_period_end
type: date
required: yes

field: metric_volume_flagged
type: int
required: yes

field: metric_precision_proxy
type: float
required: no
description: Derived from investigator labels.

field: metric_explanation_actionable_rate
type: float
required: no

field: metric_drift_score
type: float
required: no
description: Drift score computed from feature distributions/score distributions.

field: drift_alert
type: bool
required: yes

field: recommended_action
type: enum
required: yes
allowed: ["no_change", "tune_threshold", "redefine_peer_group", "pause_indicator", "retire_indicator", "investigate_data_issue"]

------------------------------------------------------------
I) Change Log & Approvals (Screen: GOV01)
------------------------------------------------------------

field: change_log_id
type: string
required: yes

field: change_type
type: enum
required: yes
allowed: ["threshold_change", "peer_group_change", "new_indicator", "model_change", "data_change", "ui_change", "security_change"]

field: change_summary
type: string
required: yes

field: change_rationale
type: string
required: yes
description: Must reference evidence (metrics, feedback, drift).

field: impacted_indicator_ids
type: array<string>
required: no

field: validation_plan_ref
type: string
required: yes
description: Link to C06 or test evidence.

field: rollback_plan
type: string
required: yes

field: approvals
type: array<object>
required: yes
object fields:
  - approver_role: enum ["pi_ops", "investigator_lead", "analytics_lead", "security_privacy", "product_owner"]
  - approver_user_id: string
  - approved: bool
  - approved_at: datetime
  - notes: string

field: effective_at
type: datetime
required: yes

field: status
type: enum
required: yes
allowed: ["proposed", "approved", "implemented", "rolled_back"]

------------------------------------------------------------
J) Pause/Discontinue (Control surface)
------------------------------------------------------------

field: pause_action
type: enum
required: no
allowed: ["pause_indicator", "resume_indicator", "retire_indicator"]

field: pause_reason
type: enum
required: no
allowed: ["performance_drop", "drift", "data_issue", "safety_concern", "policy_change", "other"]

field: pause_notes
type: string
required: no

field: pause_authorized_by_user_id
type: string
required: no

field: pause_authorized_at
type: datetime
required: no
```


***

## Implementation notes (so your UI enforces the accelerator’s “human elements”)

- **No go-live** unless C06 acceptance is signed and MON01 dashboard exists, supporting M‑25‑21’s emphasis on testing/validation and continuous monitoring.
- Every analyst/investigator action produces a structured **feedback record** (FB01), so the system can compute precision proxies and explanation usefulness, which is essential for ongoing validation and for pause/discontinue triggers.
- The GOV01 change log is mandatory for threshold/model changes, supporting accountability and traceability expectations emphasized in M‑25‑21.

If you want the next artifact, I recommend generating **`/core/ui/screens_spec.md`** (screen-by-screen user stories + permissions matrix + navigation flow) so your dev team can implement v0.1 without ambiguity.


# Congressional Housing-Oversight Research Dossier

**Air Force / Space Force housing scorecard mandates — statutory basis for the chiliAI housing demo templates**

Date: 2026-07-06. Branch: `af_housing`. Status: final.

---

## 1. Scope note

This dossier is bounded to a fixed source set, worked deeply, rather than an open-ended literature survey. The sources worked:

- **CRS R48899**, *FY2026 NDAA: Military Construction and Housing Authorizations* (Apr. 8, 2026) — https://www.congress.gov/crs_external_products/R/PDF/R48899/R48899.1.pdf (read in full)
- **CRS R47728**, *Military Housing* [Frequently Asked Questions] (Sept. 29, 2023), including Appendix B — https://www.congress.gov/crs_external_products/R/PDF/R47728/R47728.4.pdf (read in full, Appendix B worked line-by-line)
- **10 U.S.C. Chapter 169**, Subchapters IV–V (§§ 2871–2894a), current text and amendment notes via uscode.house.gov (OLRC preliminary edition); §§ 2884, 2890, 2891c, 2894, 2894a, 2856b verified section-by-section
- **FY2020 NDAA**, P.L. 116-92, Title XXX (as cataloged section-by-section in R47728 Appendix B)
- **FY2024 NDAA**, P.L. 118-31, §§ 2831–2838 (via CRS IN12229 and the OLRC source credits for 10 U.S.C. § 2856b)
- **FY2026 NDAA**, P.L. 119-60, §§ 2822–2831 and 2852 (via CRS R48899 and OLRC amendment notes)
- **GAO-23-105377**, *Military Housing: DOD Can Further Strengthen Oversight of Its Privatized Housing Program* (Apr. 2023) — https://www.gao.gov/assets/gao-23-105377.pdf (highlights and findings read)
- **GAO-23-105797**, *Military Barracks: Poor Living Conditions Undermine Quality of Life and Readiness* (Sept. 2023) — https://www.gao.gov/products/gao-23-105797 (highlights and condition-assessment findings read)
- **CRS R48137**, *Privatized Military Housing: Costs and Budgetary Issues for Congress* (July 25, 2024) — identified and used as supporting context only (https://www.congress.gov/crs-product/R48137)

Two corrections to the mission's scouting materials, found during verification and carried throughout:

1. **GAO report numbering.** GAO-23-105377 is the *privatized housing (MHPI) oversight* report (Apr. 2023, 19 recommendations). The *barracks condition* report the scouting pass described is **GAO-23-105797** (Sept. 2023, 31 recommendations). Both are worked here.
2. **§ 2884(c) cadence and element count.** The MHPI program evaluation report is now **semi-annual** with **18 enumerated elements** — P.L. 119-60 changed the cadence from annual and added elements (15)–(18); per-installation disaggregation is codified as element (18), not a freestanding requirement (OLRC amendment notes to 10 U.S.C. § 2884).

Claims below cite the statute where the statute is the authority, and the CRS/GAO product where the fact originates there. Anything that could not be verified against this source set is flagged explicitly rather than asserted.

**Key honesty caveat, stated up front:** no statute in this set mandates a literal "housing scorecard." The demo's scorecards are a presentation construct. The congressionally mandated instruments they draw from — and to which every proposed metric traces — are cataloged in § 2. See § 7 (Honest simplifications).

---

## 2. Instrument catalog

Each entry gives: citation (statute plus originating NDAA section), producer, cadence, and the required elements enumerated precisely.

### 2.A — MHPI budget-justification reporting — 10 U.S.C. § 2884(b)

- **Citation:** 10 U.S.C. § 2884(b) (Subchapter IV — the Military Housing Privatization Initiative statute). Restructured by P.L. 112-239 (FY2013 NDAA).
- **Producer / cadence:** Secretary of Defense, annually, within budget justification materials submitted to Congress.
- **Required elements** (verified against uscode.house.gov):
  1. Separate reports on expenditures and receipts of each Fund established under § 2883, identifying the construction/acquisition projects funds were transferred from and the privatization projects receiving them;
  2. Basic allowance for housing (BAH) payments and housing-unit counts, reported armed-force-by-armed-force;
  3. Description of housing privatization activities planned for the budget year and the future-years defense program period;
  4. Identification of general/flag-officer family housing units exceeding $50,000 in annual operation, maintenance, and repair costs.
- **Demo relevance:** grounds the BAH/market context feeds (`bah_rates`, `market_availability`); no scorecard threshold derives from it.

### 2.B — MHPI program evaluation report — 10 U.S.C. § 2884(c)–(d) — the central MFH instrument

- **Citation:** 10 U.S.C. § 2884(c). Elements (7)–(14) added by P.L. 116-92 (FY2020 NDAA § 3016, which also created the complaint database and incentive-fee publication duties — CRS R47728 App. B); reporting duty extended to each "Secretary concerned" by P.L. 116-283 (FY2021 NDAA); annual loan-restructuring briefing added by P.L. 117-263 (FY2023 NDAA § 2823, covering MHPI projects expected to require loan restructuring over the trailing 12 months — R47728 App. B); **cadence changed from annual to semi-annual and elements (15)–(18) added by P.L. 119-60 (FY2026 NDAA § 2823)** (OLRC amendment notes; CRS R48899 p. 7).
- **Producer / cadence:** the Secretary concerned (for DAF housing: Secretary of the Air Force), **semi-annually**, to the congressional defense committees.
- **Required evaluation elements** (18 total; verified against uscode.house.gov, paraphrased closely):
  1. Maintenance and repair backlog assessment, with cost estimates to eliminate the backlog;
  2. Financial risk mitigation plans where **project debt service exceeds net operating income** or **occupancy falls below 75 percent**;
  3. Significant variances between actual and projected recapitalization-account deposits;
  4. Details of substantial recapitalization-account withdrawals and their impact;
  5. Assessment of information requested from but not provided by private-sector housing managers;
  6. Utility costs compared with local-area rates;
  7. Housing condition assessment based on **average unit age and estimated time until recapitalization**;
  8. Assessment of **tenant complaints**;
  9. Assessment of **maintenance response times and completion of maintenance requests**;
  10. Assessment of the **dispute-resolution process, by installation, and the final outcome of each case** (including analysis of each denied rent-withholding request and each landlord-favorable outcome — R47728 App. B on FY2020 § 3016);
  11. Overall **customer service** assessment;
  12. Results of **no-notice housing inspections**;
  13. **Resident survey** findings;
  14. **Lead-based paint** data by military department (unit counts, uninspected units, abatement/mitigation efforts, TSCA § 408 compliance certification);
  15. Explanations and sources of housing data *(added by P.L. 119-60)*;
  16. Assessment of how data are used in on-base housing decisions *(added by P.L. 119-60)*;
  17. Tenant-satisfaction data limitations and the collection process *(added by P.L. 119-60)*;
  18. **Disaggregation of information by installation and by project** *(added by P.L. 119-60)* — the element that makes an installation-scoped dashboard the natural presentation of this report.
- **Unverified nuance:** the scouting pass described the occupancy trigger as "below 75% *for more than 1 year*." The current statutory text summary obtained shows the 75 percent trigger without a duration qualifier; the one-year clause could not be verified in this pass and is not relied on.

### 2.C — MHPI Tenant Bill of Rights — 10 U.S.C. § 2890

- **Citation:** 10 U.S.C. § 2890, "Rights and responsibilities of tenants of housing units." Created by P.L. 116-92 (FY2020 NDAA § 3011, which added all of Subchapter V); amended by P.L. 116-283 and P.L. 118-31 (reprisal-investigation authority moved to the DOD Inspector General; 10-day legal-counsel review of NDAs).
- **Producer / cadence:** Secretary of Defense develops and maintains the Tenant Bill of Rights and Tenant Responsibilities documents; documents submitted to Congress biennially, with 30-day advance notice of changes.
- **Enumerated rights (18)**, in brief: habitable housing meeting health/environmental standards; working fixtures, appliances, and utilities; access to the unit's 7-year maintenance history before lease signing (§ 2892a); a clear written lease; a plain-language rights briefing; move-in/move-out inspections; reporting without fear of reprisal; access to a tenant advocate; professional property management; convenient maintenance communication; electronic work-order system access with progress tracking (§ 2892); prompt professional maintenance with required timeframes; legal assistance for dispute resolution; a formal dispute-resolution process with potential rent reduction (§ 2894); BAH segregation during disputes; advance notice of entry; protection from arbitrary fees; standardized documents across installations.
- **Implementation status note:** as of December 2022, all 18 rights were available at all but three Air Force installations (GAO-23-105377 p. 12, via R47728 n.60).
- **Demo relevance:** frames the resident-experience feed; the electronic work-order system (§ 2892) is the statutory source of work-order data as a category.

### 2.D — Landlord performance and financial transparency framework — 10 U.S.C. § 2891c — the MFH category frame

- **Citation:** 10 U.S.C. § 2891c, "Transparency regarding finances and performance metrics." Created by P.L. 116-92 (FY2020 NDAA § 3016); amended by P.L. 116-283 (FY2021 NDAA § 2814: performance-metric assessments made available to tenants on request at the installation housing office — R47728 App. B); **amended by P.L. 119-60 § 2825 (FY2026 NDAA) to add insurance-policy disclosures and the total amount of payments landlords made "pursuant to a dispute resolution process"** (OLRC amendment notes; CRS R48899 p. 7).
- **Producer / cadence:** MHPI landlords submit financial and performance information to the Secretary **not less frequently than annually**; the Secretary conducts performance assessments and makes them available to tenants.
- **Required minimum performance-metric categories** (statutory minimum, verbatim category names): **(1) tenant satisfaction, (2) maintenance management, (3) safety, (4) financial management.**
- **Incentive-fee disclosure:** the applicable incentive fees, the metrics used to determine them, whether fees were paid in full or withheld partially/completely, and the reasons for withholding. Landlord annual financial reports also itemize base/asset-management/preferred-return/deferred fees and residual cash flow (FY2020 § 3016 — R47728 App. B). The Secretary concerned may withhold incentive fees from landlords showing "a propensity for failing to remedy" health or environmental hazards (10 U.S.C. § 2893, from FY2020 § 3021).
- **Demo relevance:** the four categories are the section skeleton of the proposed MFH template (§ 4.2).

### 2.E — Tenant satisfaction survey — FY2020 NDAA § 3058

- **Citation:** P.L. 116-92 § 3058, "Satisfaction survey for tenants of military housing" (uncodified; R47728 App. B).
- **Requirement:** the Secretary of Defense must require **the same satisfaction survey at every installation, for tenants of military housing including privatized military housing** — a uniform instrument across government-owned and MHPI housing.
- **Administration in practice:** conducted annually as the "DOD Annual Tenant Satisfaction Survey" by a neutral third-party firm, CEL & Associates, Inc. The DAF's 2025 cycle covers **all DAF privatized and government-owned housing sites** (af.mil / afcec.af.mil survey announcements; petersonschriever.spaceforce.mil 2025 announcement).
- **Benchmark:** in the December 2020–February 2021 cycle, Air Force residents across 68 locations scored privatized housing an average of **77.2**, characterized as "very good" by industry standards and above the Air Force target (af.mil; militaryspot.com coverage). Used here as a calibration anchor, not a statutory threshold.

### 2.F — Dispute resolution process and complaint database — 10 U.S.C. §§ 2894, 2894a

- **Citation:** 10 U.S.C. § 2894, "Landlord-tenant dispute resolution process and treatment of certain payments during process," created by P.L. 116-92 (FY2020 NDAA § 3022), amended by P.L. 116-283 (FY2021 NDAA § 2811, which also imposed **an annual report listing dispute-resolution cases by installation and the outcome of each case** — R47728 App. B). 10 U.S.C. § 2894a, "Complaint database," created by P.L. 116-92 (FY2020 § 3016); amended by P.L. 118-159 (FY2025 NDAA, "covered dwelling units" definitions).
- **Producer:** installation/regional commanders adjudicate; the Secretary of Defense maintains the publicly available complaint database; every dispute is recorded in it.
- **Statutory timelines and mechanics** (verified against uscode.house.gov):
  - **2 business days** — tenant notified, copies transmitted to relevant parties after a dispute request;
  - **7 business days** — housing management office completes its investigation;
  - **30 calendar days** (extendable to **60** with Secretary of Defense approval in limited circumstances) — deciding commander issues a decision;
  - **≥ 10 business days** — landlord remediation period;
  - **Rent segregation** — at the tenant's request, BAH (37 U.S.C. § 403) or allotted pay (10 U.S.C. § 2882(c)) is segregated from the landlord pending resolution, limited to periods when the unit fails DOD maintenance standards or state/local habitability law;
  - **10 percent rent reduction per 5-calendar-day period** of continued non-remediation after the landlord misses the remediation deadline.
- **Complaint database (§ 2894a):** records installation, responsible landlord, and nature of complaint; public; no PII; landlord responses included.
- **Refinement of the scouting pass:** the "2/7/30–60-day" timeline claim is confirmed, with 2 and 7 being *business* days, 30–60 *calendar* days, plus the ≥10-business-day remediation period. The "annual per-installation case report" originates in FY2021 NDAA § 2811 and is mirrored inside § 2884(c) element (10).

### 2.G — Unaccompanied housing mandates — FY2024 NDAA (P.L. 118-31) §§ 2831–2838, with FY2022 predecessor

The FY2024 NDAA is the UH (barracks/dorm) counterpart to the FY2020 MHPI reforms. Per CRS IN12229 and OLRC source credits:

- **§ 2831** — amends 10 U.S.C. § 2856: the Secretary of Defense must establish and enforce standards for UH facilities on **design, floor space, and level of maintenance**; compliance within two years.
- **§ 2832** — creates **10 U.S.C. § 2856b, "Covered military unaccompanied housing: standards for habitability"**: uniform minimum standards addressing condition; habitability, health, and environmental comfort; safety and security (referencing DoD Manual 4165.63). Only a military-department Secretary may waive them (§ 2856b(b)).
- **§ 2833** — creates 10 U.S.C. § 2856a: waiver procedures; Secretaries must exhaust alternatives (private housing, unit-integrity policy changes, BAH authorization) before waiving standards.
- **§ 2834** — adds **§ 2856b(c): annual certification, submitted with the President's budget, that UH repair and improvement needs "do not exceed 20 percent of the replacement cost"** of the facility. Certified by each military-department Secretary to the congressional defense committees. **This is the single hardest statutory number in the UH domain** (verified against uscode.house.gov text of § 2856b).
- **§ 2835** — pilot program to replace substandard enlisted barracks using O&M or unspecified-minor-MILCON funding.
- **§ 2836** — a civilian employee in each installation housing office to oversee UH facilities and issues.
- **§ 2837** — Secretary of Defense must issue rules for managing UH maintenance **work orders** and **"establish performance metrics to track the maintenance work performed."** Statute mandates metrics but sets no numeric targets.
- **§ 2838** — a **DOD-wide index for evaluating the condition of unaccompanied housing facilities.** No numeric bands in statute; DOD's existing condition-score convention is 90–100 good, 80–89 fair, 60–79 poor, 0–59 failing (GAO-23-105797 p. 11 n.17).
- **Predecessor threshold — FY2022 NDAA (P.L. 117-81) § 2814:** for FY2022–FY2026, each Secretary must invest FSRM funds in UH improvement equal to **5 percent of the estimated replacement cost of the total UH inventory** annually (R47728 App. B). A funding-input floor, not a condition metric.
- **Correction to the scouting pass:** the scouting summary bundled these as "§§ 2834–2838." The precise mapping is: habitability standards § 2832 (→ § 2856b); **20% certification § 2834** (→ § 2856b(c)); **work-order metrics § 2837**; **condition index § 2838**.

### 2.H — FY2026 NDAA housing provisions — P.L. 119-60 §§ 2822–2831, 2852 (per CRS R48899 pp. 7–8)

- **§ 2822** — UH annual reports to Congress must now include **waivers granted for "health and safety standards," defined to include "standards relating to mold, ventilation, fire safety, or other related habitability conditions necessary to ensure safe occupancy."** (Scouting claim verified.)
- **§ 2823** — amends the MHPI periodic reports (10 U.S.C. § 2884(c)): additional analysis of housing data and **disaggregation of certain MHPI data by military installation**; with the OLRC notes, this is the semi-annual cadence change plus elements (15)–(18). (Scouting claim verified and sharpened.)
- **§ 2824** — modifies **how and when a privatized housing company may close maintenance work orders**.
- **§ 2825** — landlords must annually provide additional financial information including **the total amount of payments made "pursuant to a dispute resolution process"** (amends § 2891c; scouting claim verified) and insurance-policy information (OLRC note).
- **§ 2826** — National Historic Preservation Act compliance for certain historic housing.
- **§ 2827** — annual data to Congress on servicemembers **whose rank would require UH residence but who receive BAH instead**, and the total BAH paid to them.
- **§ 2829** — pilot program on **emerging moisture-control/mitigation technologies** in mold-prone housing.
- **§ 2830** — **uniform mold-remediation guidelines** for military housing.
- **§ 2831** — a **standard inspection and audit program covering both privatized and government-owned military housing, using independent qualified home inspectors**.
- **§ 2852** — directs implementation of GAO recommendations on housing affordability in high-cost areas (GAO-25-106208).
- (There is no § 2828 housing provision described in R48899.)

### 2.I — Housing Requirements and Market Analysis (HRMA) — FY2023 NDAA § 2821

- **Citation:** P.L. 117-263 § 2821 (R47728 App. B): codifies the requirement that each military service conduct an **HRMA at least once every five years per installation** — an assessment of the suitability and availability of the private-sector rental housing market.
- **Demo relevance:** this is the statutory hook for the market-side feeds (`bah_rates`, `market_availability`, `area_demographics`) and the supply/affordability metrics: HRMA is the instrument that compares on-base requirements with local market capacity.

### 2.J — Supporting subchapter V machinery (brief)

For completeness of the oversight picture (all created by FY2020 NDAA Title XXX unless noted; headings verified against the uscode.house.gov subchapter V table of contents): § 2891 (contract requirements for housing units), § 2891a (management requirements — including mold inspection of vacant units before move-in, added by FY2023 § 2824), § 2891b (consideration of landlord past performance in new MHPI contracts), § 2892 (electronic maintenance work-order system), § 2892a (tenant access to 7-year maintenance history), § 2892b (PII protections in maintenance requests), § 2893 (incentive-fee withholding for unremedied health/environmental hazards). Uncodified FY2020 instruments: § 3051 uniform code of basic housing standards (extended to government-owned family housing by FY2021 § 2818), § 3052 hazard assessment tool (mold, lead, asbestos, CO, security), § 3053 environmental health hazard process, § 3061 radon testing consistent with national standards.

### 2.K — GAO oversight baseline

- **GAO-23-105377** (Apr. 2023, privatized housing): 19 recommendations. Found DOD implemented the FY2020 reforms but with gaps: dispute-resolution guidance lacking detail, tenant-advocate roles unclear, and pre-occupancy inspections using inconsistent standards so "homes with similar issues receiv[ed] different ratings." Confirms 99% of domestic family housing privatized, ~203,300 units, 14 companies, 78 projects (Highlights; R47728 pp. 9, 29).
- **GAO-23-105797** (Sept. 2023, barracks): 31 recommendations (DOD concurred with 23, partially with 8). Central finding: **DOD condition assessments are unreliable** — barracks at 7 of 10 visited installations needed major work despite condition scores above 80; one uninhabitable barracks scored above 90; of Air Force dorms considered at risk of significant degradation, **nearly 50 percent carried a condition score of 80 or above**. Documents the DOD score bands (90–100 good / 80–89 fair / 60–79 poor / 0–59 failing) and that **the Air Force relies on the building condition index** rather than the facility condition index, assessing dorms about every 4 years (policy: 5). This report is why the FY2024 §§ 2837–2838 metrics exist.

---

## 3. Metric catalog table

Every quantifiable element found in the instruments above, whether or not the demo can represent it. Directions: HB = higher-is-better, LB = lower-is-better. Feed columns are those frozen in the mission feed-column contract (`umd_authorizations`, `bah_rates`, `housing_inventory`, `market_availability`, `area_demographics`, `resident_experience`).

| Metric id | Statutory basis | Direction | Statutory threshold | Demo feed mapping |
|---|---|---|---|---|
| `maintenance_repair_backlog` | § 2884(c)(1) | LB | none (report + cost-to-eliminate) | `housing_inventory.repair_backlog_usd` |
| `debt_service_vs_noi` | § 2884(c)(2) | LB (trigger) | trigger: debt service > net operating income | **not representable** (no project-finance columns) |
| `occupancy_rate` | § 2884(c)(2) | HB (trigger) | trigger: occupancy < 75% | `housing_inventory.utilization_rate` |
| `recap_account_variance` | § 2884(c)(3)–(4) | n/a | none | **not representable** |
| `utility_cost_variance` | § 2884(c)(6) | LB | none | **not representable** |
| `average_unit_age` | § 2884(c)(7) | LB | none (age + time-to-recapitalization) | `housing_inventory.average_unit_age_years` |
| `tenant_complaints` | § 2884(c)(8); § 2894a | LB | none | proxied by `resident_experience.disputes_filed` |
| `maintenance_response_time` | § 2884(c)(9); FY2024 § 2837 | LB | none | `resident_experience.maintenance_response_hours` |
| `maintenance_completion` | § 2884(c)(9); FY2024 § 2837; FY2026 § 2824 | HB | none | `resident_experience.work_order_completion_rate`, `work_orders_open`, `work_orders_overdue` |
| `dispute_outcomes` | § 2884(c)(10); § 2894; FY2021 § 2811 | HB (resolution) | process timelines: 2/7/30–60 days; ≥10-day remediation; 10%-per-5-day rent reduction | `resident_experience.disputes_filed`, `disputes_resolved` (timelines **not representable** — no case-level data) |
| `customer_service` | § 2884(c)(11) | HB | none | proxied by `resident_experience.satisfaction_score` |
| `no_notice_inspections` | § 2884(c)(12); FY2026 § 2831 | n/a | none | **not representable** |
| `resident_survey_score` | § 2884(c)(13); FY2020 § 3058 | HB | none (DAF 2020–21 average 77.2 as practice anchor) | `resident_experience.satisfaction_score` |
| `lead_paint_units` | § 2884(c)(14) | LB | TSCA § 408 compliance certification | **not representable** |
| `landlord_perf_categories` | § 2891c | n/a | four minimum categories | section structure of MFH template |
| `incentive_fee_disclosure` | § 2891c; § 2893 | n/a | none | **not representable** |
| `dispute_payments_total` | § 2891c as amended by FY2026 § 2825 | LB (disclosure) | none | `resident_experience.dispute_payments_usd` |
| `uh_repair_to_replacement` | 10 U.S.C. § 2856b(c) (FY2024 § 2834) | LB | **cert requires ≤ 20% of replacement cost** | `housing_inventory.repair_backlog_usd` ÷ `replacement_cost_usd` |
| `uh_condition_index` | FY2024 § 2838 | HB | none (DOD bands: ≥90 good / 80–89 fair / 60–79 poor / <60 failing, GAO-23-105797 n.17) | `housing_inventory.condition_index` |
| `uh_work_order_metrics` | FY2024 § 2837 | mixed | none | `resident_experience.work_order_*` columns |
| `uh_safety_waivers` | FY2026 § 2822; § 2856b(b) | LB | none (count reported) | `resident_experience.safety_waiver_count` |
| `uh_fsrm_investment_floor` | FY2022 § 2814 | HB (input floor) | ≥ 5% of UH replacement cost, FY2022–FY2026 | **not representable** (no funding columns) |
| `bah_in_lieu_of_uh` | FY2026 § 2827 | LB | none | **not representable** (no personnel-level columns) |
| `hrma_market_adequacy` | FY2023 § 2821 (HRMA) | HB | none (5-year cadence) | `market_availability.affordability_index`, `available_rentals`; `bah_rates.*`; `area_demographics.*` |
| `supply_vs_authorization` | demo construct in support of HRMA/§ 2884(b)(2) demand context | HB | none | `housing_inventory.available_units` ÷ `umd_authorizations.*_authorized` |

---

## 4. Proposed scorecard templates

These are the concrete metric sets Task 5 implements in `backend/config/defaults/department_air_force_housing.yaml`. Constraints honored: inputs reference only frozen feed columns; formulas use only `ratio` / `sum` / `mean` / `weighted_mean` / `latest`; thresholds use `pass_min`/`warn_min`/`fail_max` for higher-is-better metrics and — per the admiral's option-(b) ruling for this mission — the mirrored `pass_max`/`warn_max`/`fail_min` keys for lower-is-better metrics (pass when value ≤ `pass_max`; warn when ≤ `warn_max`; fail when ≥ `fail_min`). Threshold provenance is labeled **[statutory]** where the statute supplies the number and **[judgement]** with rationale otherwise. `freshness_days` 90 tracks the quarterly demo snapshot cadence; 400 marks metrics whose statutory instrument is annual (survey, certification) so a yearly refresh stays fresh.

**Grading-safety data rules for Task 4's fixtures:** `replacement_cost_usd` > 0 and `disputes_filed` ≥ 1 on every row feeding a ratio denominator (a zero denominator degrades the metric to `incomplete`, not a wrong grade — `backend/scorecards/evaluation.py` raises on zero and non-finite values).

### 4.1 PROPOSED UH TEMPLATE (`uh_scorecard`, category UH, scope installation, period quarterly)

| # | Section | Metric id | Label | Unit | Direction | Formula sketch | Thresholds | Freshness | Traceability |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `demand_supply` — Demand and Supply | `uh_supply_ratio` | UH Supply Ratio | ratio | HB | `ratio`: num = `housing_inventory.available_units` (filter category=UH), den = `umd_authorizations.unaccompanied_authorized` | pass_min 1.0 / warn_min 0.9 / fail_max 0.89 — **[judgement]** 1:1 coverage of authorized unaccompanied demand; demo construct supporting HRMA-style requirements analysis | 90 | FY2023 § 2821 (HRMA context); demo construct |
| 2 | `demand_supply` | `uh_utilization_rate` | UH Utilization Rate | ratio | HB | `mean`: `housing_inventory.utilization_rate` (UH) | pass_min 0.90 / warn_min 0.75 / fail_max 0.7499 — **[judgement]** 0.75 warn boundary borrowed *by analogy* from the § 2884(c)(2) MFH occupancy trigger; 0.90 healthy-dorm-management target | 90 | § 2884(c)(2) analog (see § 6 caveat) |
| 3 | `condition_recapitalization` — Condition and Recapitalization | `uh_condition_index` | UH Condition Index | score (0–100) | HB | `weighted_mean`: value = `housing_inventory.condition_index` (UH), weight = `housing_inventory.available_units` (UH) | pass_min 80 / warn_min 60 / fail_max 59.99 — **[judgement, DOD-band-aligned]** pass = fair-or-better, warn = poor band, fail = failing band per DOD convention (GAO-23-105797 p. 11 n.17) | 90 | FY2024 § 2838 (DOD-wide UH condition index) |
| 4 | `condition_recapitalization` | `uh_repair_backlog_ratio` | Repair Backlog vs Replacement Cost | ratio | LB | `ratio`: num = `housing_inventory.repair_backlog_usd` (UH), den = `housing_inventory.replacement_cost_usd` (UH) | **pass_max 0.20 [statutory: 10 U.S.C. § 2856b(c)]** / warn_max 0.25 **[judgement]** buffer above the certification line / fail_min 0.2501 | 400 (annual certification with President's budget) | FY2024 § 2834 → § 2856b(c) |
| 5 | `maintenance_performance` — Maintenance Performance | `uh_work_order_completion_rate` | Work-Order Completion Rate | ratio | HB | `mean`: `resident_experience.work_order_completion_rate` (UH) | pass_min 0.90 / warn_min 0.80 / fail_max 0.79 — **[judgement]** statute mandates metrics but sets no target; 90% completion is a conventional facilities KPI | 90 | FY2024 § 2837; § 2884(c)(9) analog |
| 6 | `maintenance_performance` | `uh_maintenance_response_hours` | Avg Maintenance Response (hrs) | hours | LB | `mean`: `resident_experience.maintenance_response_hours` (UH) | pass_max 24 / warn_max 48 / fail_min 48.01 — **[judgement]** anchored to the 24-hour emergency/urgent response convention in DOD housing management practice; statute requires tracking response times without a number | 90 | FY2024 § 2837; § 2884(c)(9) analog |
| 7 | `resident_experience_safety` — Resident Experience and Safety | `uh_resident_satisfaction` | Resident Satisfaction Score | score (0–100) | HB | `mean`: `resident_experience.satisfaction_score` (UH) | pass_min 75 / warn_min 65 / fail_max 64.99 — **[judgement]** calibrated to the DAF 77.2 average and CEL's "very good" band; no statutory target exists | 400 (annual survey) | FY2020 § 3058 (uniform survey incl. government-owned housing) |
| 8 | `resident_experience_safety` | `uh_safety_waiver_count` | Health/Safety Standard Waivers | count | LB | `sum`: `resident_experience.safety_waiver_count` (UH) | pass_max 0 / warn_max 2 / fail_min 3 — **[judgement]** statute mandates reporting waiver counts with no threshold; zero open waivers is the only defensible healthy state, small non-zero counts warn | 90 | FY2026 § 2822; § 2856b(b) waiver authority |

### 4.2 PROPOSED MFH TEMPLATE (`mfh_scorecard`, category MFH, scope installation, period quarterly)

Sections 2–6 implement the § 2891c minimum categories (financial management, maintenance management, tenant satisfaction, safety) plus the § 2894 dispute-resolution instrument.

| # | Section | Metric id | Label | Unit | Direction | Formula sketch | Thresholds | Freshness | Traceability |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `family_housing_supply` — Supply and Market | `mfh_supply_ratio` | MFH Supply Ratio | ratio | HB | `ratio`: num = `housing_inventory.available_units` (MFH), den = `umd_authorizations.accompanied_authorized` | pass_min 1.0 / warn_min 0.9 / fail_max 0.89 — **[judgement]** as UH #1 | 90 | FY2023 § 2821 (HRMA context); demo construct |
| 2 | `family_housing_supply` | `mfh_market_affordability` | Local Market Affordability | index | HB | `mean`: `market_availability.affordability_index` | pass_min 80 / warn_min 65 / fail_max 64.99 — **[judgement]** carried from existing pack; index is a synthetic HRMA-style composite | 90 | FY2023 § 2821 (HRMA); § 2884(b)(2) BAH context |
| 3 | `financial_management` — Financial Management (§ 2891c cat. 4) | `mfh_occupancy_rate` | MFH Occupancy Rate | ratio | HB | `mean`: `housing_inventory.utilization_rate` (MFH) | pass_min 0.90 **[judgement]** healthy project / **warn_min 0.75 [statutory boundary: § 2884(c)(2) financial-risk trigger]** / fail_max 0.7499 (below the trigger) | 90 | § 2884(c)(2); § 2891c(financial management) |
| 4 | `financial_management` | `mfh_repair_backlog_ratio` | Repair Backlog vs Replacement Cost | ratio | LB | `ratio`: num = `housing_inventory.repair_backlog_usd` (MFH), den = `housing_inventory.replacement_cost_usd` (MFH) | pass_max 0.20 / warn_max 0.30 / fail_min 0.3001 — **[judgement]** parity with the UH statutory 20% line; § 2884(c)(1) mandates backlog reporting with no number; wider warn band because MFH recapitalization is project-financed | 400 | § 2884(c)(1); threshold parity with § 2856b(c) |
| 5 | `condition_recapitalization` — Condition and Recapitalization | `mfh_condition_index` | MFH Condition Index | score (0–100) | HB | `weighted_mean`: value = `housing_inventory.condition_index` (MFH), weight = `housing_inventory.available_units` (MFH) | pass_min 80 / warn_min 60 / fail_max 59.99 — **[judgement, DOD-band-aligned]** as UH #3 | 90 | § 2884(c)(7); DOD bands per GAO-23-105797 |
| 6 | `condition_recapitalization` | `mfh_average_unit_age` | Average Unit Age (yrs) | years | LB | `mean`: `housing_inventory.average_unit_age_years` (MFH) | pass_max 25 / warn_max 40 / fail_min 40.01 — **[judgement]** § 2884(c)(7) requires age-based condition assessment with no threshold; bands reflect multi-decade MHPI recapitalization planning horizons | 90 | § 2884(c)(7) |
| 7 | `maintenance_management` — Maintenance Management (§ 2891c cat. 2) | `mfh_work_order_completion_rate` | Work-Order Completion Rate | ratio | HB | `mean`: `resident_experience.work_order_completion_rate` (MFH) | pass_min 0.90 / warn_min 0.80 / fail_max 0.79 — **[judgement]** as UH #5 | 90 | § 2884(c)(9); § 2891c(maintenance management); FY2026 § 2824 |
| 8 | `maintenance_management` | `mfh_maintenance_response_hours` | Avg Maintenance Response (hrs) | hours | LB | `mean`: `resident_experience.maintenance_response_hours` (MFH) | pass_max 24 / warn_max 48 / fail_min 48.01 — **[judgement]** as UH #6 | 90 | § 2884(c)(9); § 2891c(maintenance management) |
| 9 | `tenant_satisfaction` — Tenant Satisfaction (§ 2891c cat. 1) | `mfh_resident_satisfaction` | Resident Satisfaction Score | score (0–100) | HB | `mean`: `resident_experience.satisfaction_score` (MFH) | pass_min 75 / warn_min 65 / fail_max 64.99 — **[judgement]** calibrated to DAF TSS 77.2 average, "very good" band | 400 | FY2020 § 3058; § 2884(c)(13); § 2891c(tenant satisfaction) |
| 10 | `safety` — Safety (§ 2891c cat. 3) | `mfh_safety_waiver_count` | Health/Safety Standard Waivers | count | LB | `sum`: `resident_experience.safety_waiver_count` (MFH) | pass_max 0 / warn_max 2 / fail_min 3 — **[judgement]** operationalizes the § 2891c "safety" category with the FY2026 § 2822 waiver-count construct; see § 6 | 90 | § 2891c(safety); FY2026 § 2822 (analog — UH-originated) |
| 11 | `dispute_resolution` — Dispute Resolution | `mfh_dispute_resolution_rate` | Dispute Resolution Rate | ratio | HB | `ratio`: num = `resident_experience.disputes_resolved` (MFH), den = `resident_experience.disputes_filed` (MFH) | pass_min 0.90 / warn_min 0.75 / fail_max 0.7499 — **[judgement]** statute defines process and timelines, not a resolution-rate target | 90 | § 2894; § 2884(c)(10); FY2021 § 2811 |
| 12 | `dispute_resolution` | `mfh_dispute_payments` | Dispute-Resolution Payments (USD) | USD | LB | `sum`: `resident_experience.dispute_payments_usd` (MFH) | pass_max 25,000 / warn_max 100,000 / fail_min 100,000.01 — **[judgement, weakest thresholds in the set]** FY2026 § 2825 mandates *disclosure* only; grading absolute dollars across differently sized installations is a demo convenience, flagged in § 6 | 90 | § 2891c as amended by FY2026 § 2825 |

Both templates keep `export_formats: [json, markdown]`, `incomplete_when_missing: true` on every metric, and stay entirely within the frozen feed-column contract — no new columns are required.

---

## 5. Air Force / Space Force specifics

- **Family housing is effectively fully privatized.** About 99% of military family housing in the United States operates under MHPI — 14 private companies, 78 projects, ~203,300 units DOD-wide (GAO-23-105377 Highlights; CRS R47728 p. 9). DAF MFH is therefore governed by the MHPI instruments: § 2884(c), § 2891c, § 2894/2894a, and the Tenant Bill of Rights. The **MFH template treats the MHPI oversight regime as its statutory frame.**
- **Dorms are government-owned.** Only seven MHPI unaccompanied-housing projects exist — five Army, two Navy, **none in the DAF** (R47728 p. 9 n.46). DAF dormitories are government-owned and fall under the UH statutes: § 2856/§ 2856a/§ 2856b and FY2024 §§ 2831–2838. The **UH template's frame is the FY2024 barracks regime.** (This confirms the scouting pass's ~98–99%-government-owned characterization directionally; the precise privatized share is "7 projects, none DAF.")
- **Residency policy.** The DAF requires Airmen and Guardians to live on base at pay grade E-3 and below, or E-4 with fewer than three years of service (R47728 n.24). As of June 2023, Department of the Air Force barracks policy — including required-residency ranks — applies to **both Air Force and Space Force** installations and members (GAO-23-105797 table note b). Space Force installations therefore carry the same UH/MFH instrument split, which is why the dashboard treats USSF bases uniformly with USAF ones.
- **Condition measurement.** The Air Force relies on the **building condition index** (operability of building systems) rather than the facility condition index (repair-vs-replace cost) for funding decisions, assessing dorms roughly every 4 years against a 5-year policy (GAO-23-105797 pp. 11–13). GAO found DAF condition data specifically suspect: **of AF dorms considered at risk of significant degradation, nearly 50% scored 80 or above** — i.e., "fair/good" on paper.
- **Tenant Satisfaction Survey administration.** The DAF contracts the DOD Annual Tenant Satisfaction Survey to CEL & Associates, Inc. (FY24 cycle launched March 4, 2024; the 2025 cycle covers all DAF **privatized and government-owned** sites) (afcec.af.mil; petersonschriever.spaceforce.mil). The 2020–21 cycle DAF privatized-housing average was **77.2 across 68 locations** ("very good" by industry benchmark).
- **Known implementation issues.** As of December 2022 the 18 Tenant Bill of Rights protections were available at all but three Air Force installations (GAO-23-105377 p. 12); GAO found DOD-wide gaps in dispute-resolution guidance, tenant-advocate role clarity, and inspection standardization (GAO-23-105377 Highlights) — the FY2026 § 2831 independent-inspector program is Congress's response to the inspection finding.
- **MHPI program evaluation report exemplar.** The § 2884(c) evaluation is submitted to the congressional defense committees; a specific published DAF exemplar was not independently retrieved and verified within this pass, and no claim is made about its public availability.

---

## 6. Honest simplifications

Where the demo thins, proxies, or departs from the statute. These are deliberate, and the dashboard's credibility depends on saying so.

1. **No statute names a "scorecard."** Congress mandates *reports, evaluations, certifications, surveys, databases, and performance-metric frameworks* — not a scorecard artifact. The demo's scorecards are a presentation layer over the § 2884(c) evaluation elements, the § 2891c four-category framework, the FY2024 UH mandates, and the § 3058 survey. The four § 2891c categories and 18 § 2884(c) elements are the closest congressional analogs to a scorecard, and the MFH template's section structure follows them.
2. **All feed data are synthetic.** Every value in the demo feeds (`umd_authorizations`, `bah_rates`, `housing_inventory`, `market_availability`, `area_demographics`, `resident_experience`) is fabricated for demonstration, calibrated so grades vary plausibly around the statutory and judgement thresholds. No real installation's condition, satisfaction, dispute, or financial data appear. The installation list itself is real and separately sourced (see the installations dataset provenance doc).
3. **Installation-level grading vs. report-level statutes.** Most instruments are department- or DOD-level reports. The demo grades per installation. This is *aligned in spirit* with § 2884(c) element (18) (per-installation disaggregation, added FY2026) and § 2884(c)(10) (per-installation dispute outcomes), but the statute nowhere requires per-installation pass/warn/fail grades.
4. **Statutory elements not representable in the demo schema** (no feed columns exist; deliberately not invented): debt-service-vs-NOI trigger (§ 2884(c)(2), the trigger's other half), recapitalization-account variances and withdrawals (§ 2884(c)(3)–(4)), unavailable-information assessment (§ 2884(c)(5)), utility-cost variance (§ 2884(c)(6)), no-notice inspection results (§ 2884(c)(12)), lead-based paint data (§ 2884(c)(14)), incentive-fee disclosures (§ 2891c), § 2894 per-case process timelines and rent-withholding mechanics (the demo has aggregate dispute counts only), FY2026 § 2824 work-order closure-rule compliance, FY2026 § 2827 BAH-in-lieu-of-UH counts, FY2022 § 2814 5%-of-replacement-cost FSRM investment floor, and complaint-database contents (§ 2894a). These appear in the § 3 catalog as "not representable."
5. **Threshold provenance is mostly judgement.** Exactly two hard statutory numbers land in the templates: the **20% repair-to-replacement certification line** (§ 2856b(c), UH metric 4) and the **75% occupancy financial-risk trigger boundary** (§ 2884(c)(2), MFH metric 3's warn line). Every other threshold is labeled judgement with its rationale in § 4; the DOD condition bands are administrative convention (documented by GAO), not statute.
6. **Direction-mirrored thresholds are a demo schema extension.** The platform grader was higher-is-better only; the `pass_max`/`warn_max`/`fail_min` mirrors used by six lower-is-better metrics were approved for this build and are not statutory language.
7. **Proxies and analogies, named:** UH `utilization_rate` warn at 0.75 borrows the *MFH project-finance* trigger by analogy — the statute does not set a dorm-occupancy floor. `satisfaction_score` proxies both § 2884(c)(11) customer service and (13) resident surveys. `disputes_filed` proxies § 2884(c)(8) tenant complaints. The MFH safety metric operationalizes the § 2891c "safety" category using the FY2026 § 2822 waiver-count construct, which Congress created for *UH* reporting. `mfh_dispute_payments` grades a figure Congress requires only to be *disclosed*, and its dollar thresholds ignore installation size. The single `condition_index` column abstracts over the FCI/BCI distinction GAO documents — and GAO-23-105797's central finding is that such scores can *overstate* real conditions, a caveat any real deployment would surface next to the metric.
8. **The FY2026 § 2823 "additional analysis" elements (15)–(17)** (data explanations/sources, data-use assessment, satisfaction-data limitations) are qualitative and appear in the demo only as this dossier and UI provenance text, not as metrics.
9. **Unverified nuance carried as such:** the ">1 year below 75% occupancy" qualifier from the scouting pass is not asserted anywhere in this dossier (see § 2.B).

---

*Prepared by the research element of the af_housing mission. Sources verified 2026-07-06 against uscode.house.gov (OLRC prelim), congress.gov CRS products R48899/R47728/IN12229/R48137, and gao.gov (GAO-23-105377, GAO-23-105797).*

# Explanation & Evidence Quality Rubric (v0.1)

## Purpose
Provides a structured rubric for investigators and SMEs to rate the usefulness of explanations and the adequacy of evidence bundles for Program Integrity indicators.

This rubric feeds:
- Evaluation metrics (explanation_usefulness, evidence_adequacy).
- Continuous improvement of indicators and UX.

---

## 1. Dimensions

For each evaluated case, reviewers score:

1) Explanation usefulness (1–5)
2) Evidence adequacy (1–5)

Optional free-text:
- “What was confusing or missing?”
- “What worked well?”

---

## 2. Explanation usefulness scale (1–5)

### Score 1 — Not useful at all
- Description:
  - I cannot understand why this entity was flagged.
  - Reason codes are vague, generic, or misleading.
- Indicators:
  - No clear link between explanation and evidence.
  - Language suggests certainty (“fraud”) without justification.
  - Reviewer would need to ignore the explanation and start from scratch.

### Score 2 — Poor
- Description:
  - I see a hint of why this was flagged, but I still need to do most of the work myself.
- Indicators:
  - Reason codes mention broad issues but lack specificity (e.g., “high utilization” with no benchmarks).
  - Important drivers are missing or under-emphasized.
  - “What this does NOT mean” is missing or unhelpful.

### Score 3 — Adequate
- Description:
  - I can understand the main reasons for the flag, but some details are unclear.
- Indicators:
  - Top reason codes align with the evidence, but may be incomplete or slightly confusing.
  - Some domain knowledge is required to connect dots.
  - “What this does NOT mean” covers the basics but could be sharper.

### Score 4 — Good
- Description:
  - I quickly understand why this was flagged and where to look in the evidence.
- Indicators:
  - Reason codes are specific and consistent with the evidence.
  - Explanations highlight critical patterns (e.g., anomalies over time, peer comparisons).
  - Limitations and non-implications are clearly stated.

### Score 5 — Excellent
- Description:
  - I can almost “see through the model’s eyes” and move directly to verification.
- Indicators:
  - Explanation is concise, specific, and well aligned with the underlying evidence.
  - Guides investigator to the most important timeline events, comparisons, or relationships.
  - “What this does NOT mean” prevents common misinterpretations.

---

## 3. Evidence adequacy scale (1–5)

### Score 1 — Inadequate
- Description:
  - I do not have enough evidence to assess the risk.
- Indicators:
  - Key data elements are missing (e.g., amounts, dates, codes, relationships).
  - Time window is clearly incomplete.
  - Evidence contradicts itself or cannot be traced back to source records.

### Score 2 — Weak
- Description:
  - Some relevant evidence is present, but major gaps remain.
- Indicators:
  - Only a subset of important events or entities is shown.
  - Cannot verify key claims made by the explanation.
  - Traceability is inconsistent.

### Score 3 — Sufficient
- Description:
  - I have enough information to form a preliminary judgment, but might need to pull additional data.
- Indicators:
  - Timeline and key events are reasonably complete.
  - Source pointers exist but may be hard to navigate.
  - Some domain-specific context (e.g., peer norm) is missing.

### Score 4 — Strong
- Description:
  - I can make a confident triage decision based on this evidence bundle.
- Indicators:
  - Relevant events are present and clearly organized.
  - Source pointers make it easy to drill deeper.
  - Comparator information (peers/benchmarks) is clear when relevant.

### Score 5 — Comprehensive
- Description:
  - I can fully understand and defend a triage decision using this bundle alone.
- Indicators:
  - Evidence covers timeline, relationships, and benchmarks as needed.
  - Traceability is robust; I can map each display element back to source.
  - The bundle also highlights limitations where appropriate.

---

## 4. Optional qualitative prompts

For reviewers, to support improvement:

- “What was the single most helpful part of the explanation?”
- “What is the most important missing piece of evidence?”
- “Which reason codes were confusing or misleading?”
- “If you had 1–2 changes to make this more useful, what would they be?”

---

## 5. Usage guidance

- Sampling:
  - Use a stratified sample across indicators, severity bands, and investigators.
- Aggregation:
  - Compute averages per indicator and per use case.
  - Track trends over time (see dashboards spec).
- Governance:
  - Sustained low scores should trigger:
    - Indicator reviews.
    - Change requests (C09).
    - UI/evidence bundling improvements.

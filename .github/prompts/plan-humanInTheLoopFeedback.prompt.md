## Plan: Human-in-the-Loop Feedback Integration

Add a feedback UI for investigators in the Provider Deep-Dive tab, and ensure feedback is reflected in both the Anomaly Feed and Case Management tabs, influencing workflow actions.

---

**Steps**

### Phase 1: Feedback UI in Provider Deep-Dive
1. Provide a feedback to each component in the "Overview" and "Policy Analysis" section in Provider Deep-Dive
  - Each component will have its own feedback state, allowing investigators to provide specific feedback on different aspects of the provider's behavior. This will enable more granular feedback and help identify specific areas of concern or improvement for each provider.
  - Feedback options for each component will include Agree, Disagree, and Need Further Review, allowing investigators to express their opinions on the accuracy and relevance of the information presented in each section.
  - Feedback for each component can be provided as a simple thumbs up/down and allowing for a more detailed comment, depending on the investigator's preference and the complexity of the information being evaluated. Do not require comments for every feedback, but provide the option for investigators to elaborate on their feedback if they choose to do so.
  - Do not make the screen too cluttered with feedback options. Consider using a collapsible feedback section or a simple icon-based feedback system to keep the UI clean and user-friendly.

2. Add a feedback section to the ProviderDive component:
   - Buttons for "Problematic",  "Legit Corner Case" and "Need Further Review"
   - Optional comment input
   - Store feedback in a shared state (e.g., React context or a top-level state in App)
   - If providers disagree with any component as listed in #1, but select "Legit Corner Case" or "OK", then the system should remind the investigator to provide a comment explaining their reasoning. This will help ensure that feedback is consistent between individual finding and overall assessment.

### Phase 2: Feedback Propagation
3. Update AnomalyFeed to display investigator feedback for each flagged item:
   - Show verdict and comment if available
   - Indicate which investigator provided feedback
   - Allow filtering/sorting by feedback status (e.g., show only items marked as "Problematic")
   - Do not make the feedback too busy or overwhelming in the Anomaly Feed. Consider using icons or color-coding to indicate feedback status without cluttering the interface.

4. Update CaseMgmt to reflect feedback:
   - Display feedback status for each case
   - Trigger different case actions/workflow steps based on feedback (e.g., escalate, close, request more info)
   - Differentiate the feedback between AnomalyFeed and CaseMgmt. In AnomalyFeed, feedback should be more concise and focused on the specific flagged item in data, while in CaseMgmt, feedback can be more detailed and tied to the overall case management process and next steps. This will help ensure that feedback is appropriately contextualized in each part of the application.

### Phase 3: State Management
5. Implement a shared feedback state accessible by ProviderDive, AnomalyFeed, and CaseMgmt:
   - Use React context or lift state to App
   - Feedback object keyed by provider/case ID, storing verdict, comment, and investigator info

### Phase 4: Verification
6. Manual verification:
   - Confirm feedback UI appears in Provider Deep-Dive - both the component level and case level feedback
   - Confirm feedback is visible in Anomaly Feed and Case Management for relevant items
   - Confirm workflow actions in Case Management change based on feedback

---

**Relevant files**
- code-starters/ui/integrity-ai.jsx — Add feedback UI to ProviderDive, propagate feedback to AnomalyFeed and CaseMgmt, implement shared state

---

**Decisions**
- Feedback is investigator-specific and tied to flagged provider/case IDs
- Feedback triggers workflow changes in Case Management (e.g., escalate, close, request more info)
- Initial implementation uses in-memory state; backend integration is out of scope for now

---

**Further Considerations**
1. For multi-investigator environments, consider feedback history or multiple feedback entries per case/provider.
2. For production, feedback should be persisted to a backend.
3. UI should clearly indicate feedback status and responsible investigator.

---

Let me know if you want to refine any part of this plan or proceed to implementation.

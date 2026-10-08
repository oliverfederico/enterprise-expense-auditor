# Evaluation Report: Before-and-After Compliance Audit Progression

## 1. Executive Summary & Core Results

This evaluation benchmarks the enterprise expense policy auditor following the **Build → Evaluate → Learn → Improve** cycle.
We evaluated **25 curated, realistic expense claims** across 5 distinct operational slices (clean compliant, clear violations, transit edge cases, client entertainment documentation, and subtle evasions/math).

| Metric | Baseline Agent (V1) | Improved LangGraph Agent (V2) | Improvement / Delta |
| :--- | :---: | :---: | :---: |
| **Status Decision Accuracy** | 100.0% | **100.0%** | `+0.0%` |
| **Disallowed Amount Accuracy** | 88.0% | **100.0%** | `+12.0%` |
| **Policy Citation Recall** | 100.0% | **100.0%** | `+0.0%` |
| **Overall Deterministic Pass Rate** | 88.0% | **100.0%** | `+12.0%` |
| **LLM Judge Groundedness (1-5)** | 4.92 / 5.0 | **5.00 / 5.0** | `+0.08` |
| **LLM Judge Actionability (1-5)** | 5.00 / 5.0 | **5.00 / 5.0** | `+0.00` |
| **LLM Judge Agreement Rate** | 96.0% | **100.0%** | `+4.0%` |

## 2. Performance Breakdown by Operational Slice

| Evaluation Slice | Total Claims | Baseline Pass Rate | Improved Pass Rate | Delta | Key Nuance Tested |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `clean_compliant` | 5 | 100.0% | **100.0%** | `+0.0%` | Clean compliant individual meals, subway, corporate hotel, client dinner. |
| `clear_violations` | 5 | 60.0% | **100.0%** | `+40.0%` | Alcohol >20% cap, solo meal >$75 per diem, unauthorized rideshare, personal incidentals. |
| `transit_edge_cases` | 5 | 100.0% | **100.0%** | `+0.0%` | Late-night exception (22:00-06:00), heavy equipment (>30 lbs), weather excuses, 14m vs 16m cutoff. |
| `client_entertainment_and_docs` | 5 | 80.0% | **100.0%** | `+20.0%` | Mandatory attendee lists, vague justifications, non-itemized receipts above/below $25. |
| `subtle_evasions_and_math` | 5 | 100.0% | **100.0%** | `+0.0%` | Same-day receipt splitting, disguised alcohol, breakfast/lunch solo drinks, multi-meal sum. |

## 3. What Did We Learn from Baseline Evaluation Failures?

### Failure Mode 1: Arithmetic & Cap Double-Counting (TC-06)
- **What happened**: The baseline agent reviewed a $130 meal with $45 alcohol ($25 excess alcohol). It disallowed $25 for alcohol, and then additionally disallowed $30 for per diem, double counting the food/drink deduction.
- **The fix**: Implemented `audit_meals_and_per_diem()` in `src/expense_auditor/tools/math_tools.py` which sequences deductions deterministically: alcohol excess is calculated first, subtracted from eligible receipts, and then daily per diem ($75) is enforced on the remaining balance without double-penalty.

### Failure Mode 2: Pre-tax vs Post-tax Deduction Confusion on Lodging (TC-10)
- **What happened**: For a $350/night hotel room where the policy limit was $200 pre-tax, the baseline agent disallowed $150 room rate plus an invented $21 proportional tax, resulting in inconsistent accounting figures.
- **The fix**: Implemented deterministic rate cap checking in `audit_lodging_and_incidentals()`, enforcing exact rule boundaries on pre-tax lodging rates.

### Failure Mode 3: Geographic & Market Tier Misclassification (TC-09)
- **What happened**: The baseline agent failed to identify Washington D.C. as a Tier 1 metropolitan area when destination was specified by hotel name rather than explicit state code.
- **The fix**: Added multi-field context inspection (matching `origin`, `destination`, and `trip_purpose`) against canonical Tier 1 metropolitan markers in `math_tools.py`.

### Failure Mode 4: Solo Per Diem vs Client Entertainment Confusion (TC-03, TC-20)
- **What happened**: The baseline agent occasionally applied the $75 individual per diem rule to client hosting dinners.
- **The fix**: Segmented meal audit logic so `CLIENT_ENTERTAINMENT` claims are strictly audited under SEC-3.2 ($150 per attendee) rather than SEC-1.1 ($75 individual per diem).

## 4. Production Evaluation & Monitoring Strategy

To safely transition this agent into production at enterprise scale:
1. **Shadow Mode Deployment (Weeks 1-4)**:
   - The auditor runs silently in parallel with human expense analysts on 100% of employee submissions.
   - Compute the human-agent agreement matrix. Track false positives (disallowing compliant claims) and false negatives (approving non-compliant claims).
2. **Confidence-Tiered Human-in-the-Loop Triage (Month 2+)**:
   - **Auto-Approve Tier**: Reports under $100 with 100% itemized receipts, no alcohol, and high confidence (>0.95) are auto-approved instantly.
   - **Review Tier**: Any report with detected violations or missing documentation is routed to finance staff with a pre-populated audit summary and employee remediation message ready for one-click approval.
3. **Online LangSmith Monitoring & Continuous Drift Detection**:
   - Sample 10% of production traces for automated LLM-as-a-judge evaluation (Groundedness & Actionability).
   - Monitor employee appeal rates: any appealed audit is flagged as a high-value edge case to expand the regression test suite.
   - Policy versioning: whenever company policies update, the automated eval suite executes as a CI/CD gate before deploying updated graph prompts or embeddings.
# Payroll Clarity — Edge case catalog

Maps product rules to automated tests under `tests/`. All data is illustrative.

| ID | Area | Edge case | Test file |
|---|---|---|---|
| EC-SEED-01 | Seed | Exactly 120 employees; country splits 50/30/22/18 | `test_seed_integrity.py` |
| EC-SEED-02 | Seed | No Philippines / 5th country | `test_seed_integrity.py` |
| EC-SEED-03 | Seed | All 120 onboarded (`date_added` null, `is_new` 0, Workday) | `test_seed_integrity.py` |
| EC-SEED-04 | Seed | Named 8 + pay/currency exact | `test_seed_integrity.py` |
| EC-SEED-05 | Seed | Priya / Arjun not in roster | `test_seed_integrity.py` |
| EC-SEED-06 | Seed | Rebuild deterministic (RNG 42) | `test_seed_integrity.py` |
| EC-SEED-07 | Seed | Unique emails; currency↔country | `test_seed_integrity.py` |
| EC-PAY-01 | Pay timing | Onboarded unchanged → green October | `test_pay_timing_edge_cases.py` |
| EC-PAY-02 | Pay timing | Missing fields before cutoff → amber | `test_pay_timing_edge_cases.py` |
| EC-PAY-03 | Pay timing | Missing after cutoff → Moved to November | `test_pay_timing_edge_cases.py` |
| EC-PAY-04 | Pay timing | Added after cutoff → November + off-cycle stub | `test_pay_timing_edge_cases.py` |
| EC-PAY-05 | Pay timing | Added exactly Oct 15 still October-eligible | `test_pay_timing_edge_cases.py` |
| EC-PAY-06 | Pay timing | 1 / 2 / 3+ missing field wording | `test_pay_timing_edge_cases.py` |
| EC-PAY-07 | Pay timing | Priya / Arjun demo personas | `test_pay_timing_edge_cases.py` |
| EC-CAL-01 | Calendar | Prototype date → stage table | `test_calendar_stage_edge_cases.py` |
| EC-CAL-02 | Calendar | Countdown: N days / 1 day / Due today / closed | `test_calendar_stage_edge_cases.py` |
| EC-CAL-03 | Calendar | Stage boundaries around 15 / 22 / 23 / 28 | `test_calendar_stage_edge_cases.py` |
| EC-CAL-04 | Calendar | Invalid date parse raises | `test_calendar_stage_edge_cases.py` |
| EC-ISS-01 | Issues | Blocking sorts before deadline_risk | `test_issue_routing_edge_cases.py` |
| EC-ISS-02 | Issues | Same severity: deadline then title | `test_issue_routing_edge_cases.py` |
| EC-ISS-03 | Issues | Resolve idempotent / unknown id noop | `test_issue_routing_edge_cases.py` |
| EC-ISS-04 | Issues | Only Lena held; Brazil has no employee hold | `test_issue_routing_edge_cases.py` |
| EC-ISS-05 | Issues | Approve blocked only by open blocking | `test_issue_routing_edge_cases.py` |
| EC-ISS-06 | Issues | Brazil owner = Country HR owner | `test_issue_routing_edge_cases.py` |
| EC-CTY-01 | Country | Oct 12 chips DE/UK/BR/IN | `test_country_status_edge_cases.py` |
| EC-CTY-02 | Country | Fix Lena → Germany On track | `test_country_status_edge_cases.py` |
| EC-CTY-03 | Country | Deadline risk beats blocking same country | `test_country_status_edge_cases.py` |
| EC-CTY-04 | Country | Empty issues → all On track | `test_country_status_edge_cases.py` |
| EC-NOT-01 | Notify | Visible iff send_date ≤ prototype date | `test_notifications_edge_cases.py` |
| EC-NOT-02 | Notify | Newest first; Oct 12 = 1 email | `test_notifications_edge_cases.py` |
| EC-NOT-03 | Notify | Slack filtered out of email channel | `test_notifications_edge_cases.py` |
| EC-NOT-04 | Notify | Oct 12 email links all 4 issue ids | `test_notifications_edge_cases.py` |
| EC-DOC-01 | Docs | Priya missing PAN/bank mappings | `test_document_fixture_edge_cases.py` |
| EC-DOC-02 | Docs | Arjun all mapped; after-cutoff start | `test_document_fixture_edge_cases.py` |
| EC-DOC-03 | Docs | Bonus £8000 resolves issue_002; base net unchanged | `test_document_fixture_edge_cases.py` |
| EC-REV-01 | Review | 6 human lines; 38/32/6 on cycle | `test_review_and_ai_edge_cases.py` |
| EC-REV-02 | Review | AI note never mutates monthly_net | `test_review_and_ai_edge_cases.py` |
| EC-REV-03 | Review | Confirm log is human, not AI | `test_review_and_ai_edge_cases.py` |
| EC-DEMO-01…08 | Demo | Full demo script domain invariants | `test_demo_script_scenarios.py` |
| EC-DEMO-09 | Demo | Resolutions persist across date change | `test_demo_script_scenarios.py` |

## UI edge cases (Phase Test — later)

To be automated with Playwright/Vitest after screens exist:

- Stub clicks never crash; show version note  
- Approve button disabled + hint while blocking open  
- Nav badge = open issue count after each resolve  
- Employees sort: new first; filters Country / Action needed  
- Review empty-state before Oct 22  
- Slack tab greyed; single CTA in email body  

## Run

```bash
cd /Users/charugupta/MultiplierPayroll
python3 -m pytest tests/ -v
```

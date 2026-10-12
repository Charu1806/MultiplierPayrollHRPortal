# Test inventory

Interactive controls and covering specs. Generated for scope-C pass; expand as `data-testid` coverage grows.

| data-testid / control | Screen | Spec |
|-----------------------|--------|------|
| people-pagination | All employees | e2e/bugs.spec.ts, e2e/inventory.spec.ts, e2e/demo.spec.ts |
| people-page-size | All employees | e2e/bugs.spec.ts |
| Pay this cycle column | All employees | e2e/bugs.spec.ts |
| Powered by Multiplier | Payroll sidebar caption | e2e/bugs.spec.ts |
| Month-driven dashboard and inbox | Overview + Notifications | e2e/dynamic-calendar.spec.ts |
| Remind / Resend reminder | Action needed | e2e/bugs.spec.ts, tests/test_remind_form_smtp.py |
| Add details myself + field validation | Action needed | e2e/bugs.spec.ts, tests/test_field_normalize.py |
| ConfirmModal | Global | Actions/People confirms; store confirmError |
| Date picker / Reset demo | Shell | e2e/inventory.spec.ts (cancel path) |
| Nav: Overview, Actions, Review, Notifications, People | Shell | e2e/inventory.spec.ts |
| Add employee Save | Add employee | e2e/inventory.spec.ts |
| payOutlook API | Employees list | tests/test_pay_outlook.py |

CI: `npm run check:hardcoding` + inventory sweep. Uncovered interactive elements should get `data-testid` and a row here.

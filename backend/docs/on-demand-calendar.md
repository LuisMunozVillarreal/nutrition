# On-demand logging calendar

`apps.plans.services.ensure_day(user, date)` resolves a day and fills all seven
days of its week. `ensure_week(user, date)` returns the complete plan;
`ensure_week_days(plan)` repairs an explicitly selected plan. These are write-side
services, not scheduled precreation and not read/query side effects. A caller
writing an intake, exercise or steps record must enclose resolution and its write
in one transaction; the GraphQL create mutations do this.

## Setup and selection

- The first plan must be configured explicitly with a measurement and nutrition
  parameters. No template means an explicit error, not invented default targets.
- Date resolution uses the latest plan starting on or before the requested date.
  Its arbitrary start weekday anchors seven-day windows; Monday is not assumed.
  Only the requested window is created, not intervening gaps.
- A newly created plan copies `protein_g_kg`, `fat_perc` and `deficit` from that
  historical template and selects the latest measurement dated on or before the
  new week start (timestamp, then primary key order). Missing historical inputs
  produce an error. Existing plans retain their own measurement and settings.
- The complete target window must not overlap another existing plan. Date-only
  resolution rejects overlapping windows, even if a conflicting day is missing.
  Legacy overlapping plans are not merged, deleted or silently selected.
- ID-based resolution verifies ownership, preserves the exact selected day and
  plan even in legacy overlaps, and repairs missing siblings in that plan only.
- Repair inserts absent dates using the plan's targets and deficit distribution.
  Existing day IDs, custom goals, tracking flags, intakes, exercises and steps are
  not rewritten. Inconsistent historical date/day-number pairs fail uniqueness
  checks rather than overwriting data.
- `tracked` retains its existing TDEE calculation meaning and `True` default;
  ensuring rows does not assert that meals/activity were logged or completed.

## GraphQL contract

`createIntake`, `createExercise`, and `createDaySteps` accept exactly one non-null
selector: existing `dayId: Int` or `dayDate: String` (ISO calendar date, normally
`YYYY-MM-DD`). Both selectors or neither are rejected. Authentication is required;
foreign and nonexistent day IDs both return `Day not found`. Date-based writes
only use the authenticated user's plans and measurements. Logging failures roll
back calendar creation/repair along with the logging write.

Existing ID-based clients remain compatible. Deploy this expanded backend before
any client starts sending `dayDate` or nullable ID variables to it; older GraphQL
servers do not accept the new contract. This change does not add frontend date
selection, external-provider integrations or a scheduler.

## Migration 0033: populated-data rollout

The migration adds uniqueness for `(user, start_date)` on weeks, `(plan, day)` and
`(plan, day_num)` on days. It performs **no data cleanup or backfill**. Partial
weeks and existing values remain untouched. Exact duplicates fail with a database
`IntegrityError`; on SQLite/PostgreSQL the atomic migration rolls back, leaves the
migration unrecorded and retains all original rows and linked logs. Reversal
removes only these constraints.

Before rollout, take a verified backup and audit a production-like restored copy.
Use a singleton migration runner with application writers paused/drained. These
ordinary unique-constraint operations scan/build indexes and acquire table locks;
this is **not** an online or lock-free migration. Plan a maintenance window based
on representative database size. Do not run the migration independently in each
replica while old writers remain active.

The following read-only SQL identifies duplicate keys (inspect results only in an
authorized private database session):

```sql
SELECT user_id, start_date, COUNT(*) FROM plans_weekplan
GROUP BY user_id, start_date HAVING COUNT(*) > 1;
SELECT plan_id, day, COUNT(*) FROM plans_day
GROUP BY plan_id, day HAVING COUNT(*) > 1;
SELECT plan_id, day_num, COUNT(*) FROM plans_day
GROUP BY plan_id, day_num HAVING COUNT(*) > 1;
```

If any duplicates exist, stop the rollout. Obtain a separately reviewed,
owner-approved reconciliation plan preserving linked logs and customized values;
do not blindly delete, merge, fake-apply the migration or retry indefinitely.
After reconciliation, rerun the audit and migration with a fresh executor. Week
window overlaps with different starts are not prohibited by these constraints;
they remain explicitly selectable by ID, but date-only writes fail closed.

`tests/plans/test_calendar_migration.py` exercises populated historical models,
linked intake/exercise/steps preservation, each duplicate key's atomic failure,
and a fresh-executor retry after test-only reconciliation. PostgreSQL-specific
row-lock contention tests are in `test_calendar_concurrency.py`; SQLite skips
those tests and cannot establish production locking correctness. PostgreSQL CI
execution remains required before merge.

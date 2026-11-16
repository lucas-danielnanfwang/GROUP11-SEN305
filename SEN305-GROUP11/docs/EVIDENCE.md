# Lab 3 In-Lab Exercise - Evidence and Submission Sheet

Environment used to produce this evidence: MySQL 8.0.46, Django 5.2.19, mysqlclient 2.3.1, Python 3 (Linux).
Database `sen305_servicedesk`, user `sen305_app` (least privilege). **Synthetic data only.**

> **Student note:** the outputs below are from my verification run. Re-run the commands on your own machine and
> paste *your* output where your lecturer asks for it. MySQL statistics differ slightly between machines, so
> the EXPLAIN in section 5 may not look identical to yours; describe what *you* observe.

## Submission details (fill in)

| Field | Entry |
|---|---|
| Student name | |
| Registration number | |
| Project link (repository URL) | |
| Final commit hash | |
| Group name | |
| Group leader | |

## Acceptance criteria

| Criterion | Pass condition | Result | Evidence |
|---|---|---|---|
| Migration discipline | A reviewed 0002 migration applies successfully | PASS | Sections 1-2 |
| Due date | Field and supporting index exist in MySQL | PASS | Section 3 |
| Resolution rule | Invalid resolved records fail `full_clean()` | PASS | Section 4 |
| Admin | Due date and resolution data visible and searchable or filterable | PASS | Section 6 |
| Query evidence | Generated SQL and explain output recorded | PASS | Section 5 |
| Tests | Original and new tests pass | PASS (27/27) | Section 7 |
| Data safety | Only synthetic laboratory data are used | PASS | every row titled `SYNTH ...` |

## 1. Migration state

`makemigrations requests_app -n add_due_at_and_resolution_summary` created `0002`; `0001_initial.py` was not edited
(its SHA-256 was identical before and after, and a test enforces that it contains no new columns).

```
requests_app
 [X] 0001_initial
 [X] 0002_add_due_at_and_resolution_summary
```

`python manage.py makemigrations --check --dry-run` -> `No changes detected`.

## 2. `sqlmigrate requests_app 0002` (reviewed before applying)

```sql
--
-- Add field due_at to servicerequest
--
ALTER TABLE `requests_app_servicerequest` ADD COLUMN `due_at` datetime(6) NULL;
--
-- Add field resolution_summary to servicerequest
--
ALTER TABLE `requests_app_servicerequest` ADD COLUMN `resolution_summary` longtext NOT NULL;
--
-- Create index req_status_due_idx on field(s) status, due_at of model servicerequest
--
CREATE INDEX `req_status_due_idx` ON `requests_app_servicerequest` (`status`, `due_at`);
```

Review notes: two `ADD COLUMN`s and one `CREATE INDEX`, nothing else. `due_at` is `NULL`-able so existing rows are
safe. `resolution_summary` is `longtext NOT NULL`; MySQL cannot give TEXT a DEFAULT, so I tested the upgrade with a
row that already existed at 0001: after migrating it had `due_at = NULL` and `resolution_summary = ''`.

## 3. Schema in MySQL

```
Table	Non_unique	Key_name	Seq_in_index	Column_name	Collation	Cardinality	Sub_part	Packed	Null	Index_type	Comment	Index_comment	Visible	Expression
requests_app_servicerequest	1	req_status_due_idx	1	status	A	0	NULL	NULL		BTREE			YES	NULL
requests_app_servicerequest	1	req_status_due_idx	2	due_at	A	0	NULL	NULL	YES	BTREE			YES	NULL
Field	Type	Null	Key	Default	Extra
due_at	datetime(6)	YES		NULL	
resolution_summary	longtext	NO		NULL
```

## 4-5. Tasks 1-3 command output (`python manage.py lab3_exercise`)

```

==============================================================================
TASK 1 step 5 - two requests with different due dates
==============================================================================
updated: 'SYNTH due-soon socket fault' due_at=2026-11-17 21:13
updated: 'SYNTH due-later projector fault' due_at=2026-11-21 21:13

Chosen time = now + 3 days = 2026-11-19 21:13 UTC
Query: ServiceRequest.objects.due_before(chosen)
SQL  : SELECT `requests_app_servicerequest`.`id`, `requests_app_servicerequest`.`requester_id`, `requests_app_servicerequest`.`category_id`, `requests_app_servicerequest`.`title`, `requests_app_servicerequest`.`description`, `requests_app_servicerequest`.`location`, `requests_app_servicerequest`.`priority`, `requests_app_servicerequest`.`status`, `requests_app_servicerequest`.`due_at`, `requests_app_servicerequest`.`resolved_at`, `requests_app_servicerequest`.`resolution_summary`, `requests_app_servicerequest`.`created_at`, `requests_app_servicerequest`.`updated_at` FROM `requests_app_servicerequest` WHERE (`requests_app_servicerequest`.`title` LIKE BINARY SYNTH% AND `requests_app_servicerequest`.`due_at` < 2026-11-19 21:13:07.928645) ORDER BY `requests_app_servicerequest`.`created_at` DESC
Result: ['SYNTH due-soon socket fault']

Index check for  WHERE status IN (active) AND due_at < chosen:
SQL  : SELECT `requests_app_servicerequest`.`id`, `requests_app_servicerequest`.`requester_id`, `requests_app_servicerequest`.`category_id`, `requests_app_servicerequest`.`title`, `requests_app_servicerequest`.`description`, `requests_app_servicerequest`.`location`, `requests_app_servicerequest`.`priority`, `requests_app_servicerequest`.`status`, `requests_app_servicerequest`.`due_at`, `requests_app_servicerequest`.`resolved_at`, `requests_app_servicerequest`.`resolution_summary`, `requests_app_servicerequest`.`created_at`, `requests_app_servicerequest`.`updated_at` FROM `requests_app_servicerequest` WHERE (`requests_app_servicerequest`.`status` IN (open, assigned, in_progress) AND `requests_app_servicerequest`.`due_at` < 2026-11-19 21:13:07.928645 AND `requests_app_servicerequest`.`title` LIKE BINARY SYNTH%)
-> Filter: (requests_app_servicerequest.title like <cache>(cast('SYNTH%' as char charset binary)))  (cost=2.11 rows=0.333)
    -> Index range scan on requests_app_servicerequest using req_status_due_idx over (status = 'assigned' AND NULL < due_at < '2026-11-19 21:13:07.928645') OR (status = 'in_progress' AND NULL < due_at < '2026-11-19 21:13:07.928645') OR (status = 'open' AND NULL < due_at < '2026-11-19 21:13:07.928645'), with index condition: ((requests_app_servicerequest.`status` in ('open','assigned','in_progress')) and (requests_app_servicerequest.due_at < TIMESTAMP'2026-11-19 21:13:07.928645'))  (cost=2.11 rows=3)


==============================================================================
TASK 2 steps 7-8 - resolution rule proved with full_clean()
==============================================================================
FAIL  RESOLVED, no resolved_at, no summary                 -> {'resolved_at': ['A resolved or closed request must have a resolved_at timestamp.'], 'resolution_summary': ['A resolved or closed request requires a resolution summary.']}
FAIL  RESOLVED, resolved_at set, summary missing           -> {'resolution_summary': ['A resolved or closed request requires a resolution summary.']}
FAIL  RESOLVED, resolved_at set, summary only spaces       -> {'resolution_summary': ['A resolved or closed request requires a resolution summary.']}
FAIL  CLOSED, summary set, resolved_at missing             -> {'resolved_at': ['A resolved or closed request must have a resolved_at timestamp.']}
PASS  RESOLVED, resolved_at + summary present              -> valid
PASS  OPEN, blank summary (rule does not apply)            -> valid

(No probe was saved:  0 rows.)

==============================================================================
TASK 3 - synthetic data and query analysis
==============================================================================
Seeded 0 new synthetic rows (12 planned).
Synthetic rows in table: 14  |  all rows in table: 14

Query: open OR assigned, category=Electrical, ORDER BY priority, created_at

queryset.query:
 SELECT `requests_app_servicerequest`.`id`, `requests_app_servicerequest`.`requester_id`, `requests_app_servicerequest`.`category_id`, `requests_app_servicerequest`.`title`, `requests_app_servicerequest`.`description`, `requests_app_servicerequest`.`location`, `requests_app_servicerequest`.`priority`, `requests_app_servicerequest`.`status`, `requests_app_servicerequest`.`due_at`, `requests_app_servicerequest`.`resolved_at`, `requests_app_servicerequest`.`resolution_summary`, `requests_app_servicerequest`.`created_at`, `requests_app_servicerequest`.`updated_at` FROM `requests_app_servicerequest` WHERE (`requests_app_servicerequest`.`category_id` = 2 AND `requests_app_servicerequest`.`status` IN (open, assigned)) ORDER BY `requests_app_servicerequest`.`priority` ASC, `requests_app_servicerequest`.`created_at` ASC

result rows (priority, status, title):
  1  open      SYNTH Electrical Open #1
  1  assigned  SYNTH Electrical Assigned #1
  3  open      SYNTH due-soon socket fault
  3  open      SYNTH due-later projector fault
  4  open      SYNTH Electrical Open #2
  4  assigned  SYNTH Electrical Assigned #2

queryset.explain():
-> Sort row IDs: requests_app_servicerequest.priority, requests_app_servicerequest.created_at  (cost=3.21 rows=6)
    -> Index range scan on requests_app_servicerequest using req_cat_status_idx over (category_id = 2 AND status = 'assigned') OR (category_id = 2 AND status = 'open'), with index condition: ((requests_app_servicerequest.category_id = 2) and (requests_app_servicerequest.`status` in ('open','assigned')))  (cost=3.21 rows=6)
```

### Reading the Task 1 index check
For `WHERE status IN ('open','assigned','in_progress') AND due_at < <chosen>` MySQL reports
`Index range scan ... using req_status_due_idx`, so the new composite index is used.

### Reading the Task 3 EXPLAIN (observed on this run)
* **Index used: `req_cat_status_idx` (category_id, status)** as an *index range scan* on
  `(category_id = 2 AND status = 'assigned') OR (category_id = 2 AND status = 'open')`.
* A `Sort row IDs: priority, created_at` step sits above it: the rows are fetched through the category/status index,
  then sorted. This is MySQL's *filesort*.
* `req_priority_date_idx (priority, created_at)` was **not** chosen. It could deliver rows already in
  `ORDER BY` order, but it cannot narrow by category or status, so MySQL would have to read and filter every row.
  (Interpretation of the optimizer's choice; the output itself only shows which index was used.)
* The table holds only 14 rows, yet MySQL still preferred the index range over a full scan on this server. If **your**
  EXPLAIN shows a full table scan instead (`type: ALL` / "Table scan"), that is also normal, and the honest explanation
  is: with so few rows, reading the whole table costs about the same as using an index, so the optimizer's
  cost-based choice is not meaningful. Write down whichever you actually see.

## 6. Admin (Task 1 step 4, Task 2 visibility)

* List columns: Title, Category, Requester, Priority, Status, **Due at**, **Overdue** (tick/cross), **Resolved at**, Created.
* Sidebar filter **"due state"**: Overdue (past due, still active) / Due in next 24 hours / Due later / No due date.
* Search box also searches **resolution_summary**.
* Change form has *Service level* and *Resolution* sections; the model rule shows its error messages there.
* Automated proof: `AdminTests` (6 tests) including a POST that Admin rejects an invalid RESOLVED request.
* Manual check: open `/admin/requests_app/servicerequest/`, then use the "due state" filter and search for a phrase
  such as `Synthetic fix`.

## 7. Test results (`python manage.py test requests_app -v 2`)

```
Found 27 test(s).
  Applying contenttypes.0001_initial... OK
  Applying auth.0001_initial... OK
  Applying admin.0001_initial... OK
  Applying admin.0002_logentry_remove_auto_add... OK
  Applying admin.0003_logentry_add_action_flag_choices... OK
  Applying contenttypes.0002_remove_content_type_name... OK
  Applying auth.0002_alter_permission_name_max_length... OK
  Applying auth.0003_alter_user_email_max_length... OK
  Applying auth.0004_alter_user_username_opts... OK
  Applying auth.0005_alter_user_last_login_null... OK
  Applying auth.0006_require_contenttypes_0002... OK
  Applying auth.0007_alter_validators_add_error_messages... OK
  Applying auth.0008_alter_user_username_max_length... OK
  Applying auth.0009_alter_user_last_name_max_length... OK
  Applying auth.0010_alter_group_name_max_length... OK
  Applying auth.0011_update_proxy_permissions... OK
  Applying auth.0012_alter_user_first_name_max_length... OK
  Applying requests_app.0001_initial... OK
  Applying requests_app.0002_add_due_at_and_resolution_summary... OK
  Applying sessions.0001_initial... OK
The rule is on the model, so Admin gets it for free. ... ok
test_changelist_shows_due_at_and_overdue_columns ... ok
test_next_24h_and_later_filters ... ok
test_none_filter_lists_requests_without_due_date ... ok
test_overdue_filter_excludes_resolved_future_and_undated ... ok
test_search_finds_request_by_resolution_summary ... ok
test_due_at_is_nullable_and_optional ... ok
test_overdue_means_past_due_and_still_active ... ok
test_status_due_index_exists_in_mysql ... ok
test_two_requests_query_those_due_before_chosen_time ... ok
test_0001_was_not_edited_to_contain_the_new_columns ... ok
test_0002_is_the_leaf_and_depends_on_0001 ... ok
test_no_model_change_is_missing_a_migration ... ok
test_closed_is_subject_to_the_same_rule ... ok
test_invalid_record_is_not_saved_when_validated_first ... ok
test_resolution_summary_defaults_to_empty_string ... ok
test_resolved_without_resolved_at_and_summary_reports_both_fields ... ok
test_resolved_without_resolved_at_is_rejected ... ok
test_resolved_without_summary_is_rejected ... ok
test_rule_does_not_apply_to_active_statuses ... ok
test_valid_resolved_record_passes_full_clean ... ok
test_whitespace_only_summary_is_rejected ... ok
test_category_in_use_is_protected ... ok
test_database_constraint_rejects_priority_six ... ok
test_default_status_is_open ... ok
test_priority_validator_rejects_zero ... ok
test_request_accepts_only_one_work_order ... ok
Ran 27 tests in 1.659s
OK
```

Mutation check (to prove the tests can fail): disabling the rule made 7 tests fail; making `overdue()` ignore status
made 2 tests fail; restoring the code made all 27 pass.

## 8. Short reflection (for the report)

* *Why a new migration instead of editing 0001?* 0001 is already applied and committed; changing it would make the
  files disagree with the database history. A new 0002 records the change as a reviewable step.
* *Why is the rule on the model?* It is a business rule about the data, so it must hold no matter whether the data
  arrives from Admin, a form, a service or a script that calls `full_clean()`.
* *Why a composite index `(status, due_at)`?* The common question is "which active requests are past due?"; equality on
  status followed by a range on due_at is exactly what a composite B-tree index serves.

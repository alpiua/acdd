# Simple-plan procedure

1. Bind one primary plan to its own milestone section.
2. Keep the planning set self-contained and every embedded task `todo`.
3. Validate required sections, task fields, prerequisite order, impact, and
   ordered receipts with `scripts/check_simple_plan.py --strict`.
4. Build receipt provenance from `.acdd/planning-input-spec.json`.
5. Run plan review in overview mode and hand task candidates to a later
   `acdd/task/v1` session.

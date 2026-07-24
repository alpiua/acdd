# ACDD Workflow

Keep profiles and contracts host-neutral. Domain owner adapters live in their
own repositories; this repository contains only its own simple-plan adapter and
copyable examples.

- Task flow: [`acdd-task`](skills/acdd-task/SKILL.md), `profiles/task/v1.yaml`.
- Plan flow: [`acdd-plan`](skills/acdd-plan/SKILL.md), `profiles/plan/v1.yaml`.
- Update the repository-owned [`PLAN.md`](PLAN.md) when contracts or embedded tasks change.
- Validate with explicit `--workspace-root` and `--adapter` arguments.
- Keep the supported profile IDs at `acdd/task/v1` and `acdd/plan/v1`.
- Run `python3 -m pytest tests -q`,
  `python3 scripts/check_markdown_links.py --root .`, and `git diff --check`.

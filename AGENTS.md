# ACDD Workflow

This plugin owns the host-neutral ACDD coordination contract.

- Keep `profiles/` and `contracts/` free of host-specific tool names.
- Keep adapter implementations outside this plugin in their owning repositories.
- Keep only methodology, contracts, routing, and generic skills here.
- Update the single plan at `../../planner/plugins/acdd-workflow.md` when scope
  or capability contracts change.
- Run `python3 scripts/validate_acdd.py`; for workspace integration add
  `--binding ../../.agents/acdd/binding.yaml --settings ../../.pi/settings.json`.
- Run `python3 -m pytest tests -q`, link validation, and `git diff --check`.

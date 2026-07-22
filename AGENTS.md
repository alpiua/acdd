# ContextUnity ACDD Workflow

This plugin owns the host-neutral ACDD coordination contract.

- Keep `profiles/` and `contracts/` free of host-specific tool names.
- Keep Planner as task/evidence authority and ContextUnity as runtime authority.
- Move one canonical skill/reference at a time; leave compatibility routers instead
  of copies.
- Update the single plan at
  `../../planner/plugins/contextunity-acdd-workflow.md` when scope or
  capability contracts change.
- Validate the Codex manifest, YAML profile/contract, links, and `git diff --check`.

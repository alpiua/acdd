# Reviewer adapter examples

These full adapters extract the review patterns used by Planner-style owner
bundles:

- [`task-adapter.yaml`](.acdd/task-adapter.yaml) owns isolated inbound
  `architecture/v1` execution and binds discovery capabilities to actual tools.
- [`implementation-adapter.yaml`](.acdd/implementation-adapter.yaml) owns the
  terminal task `review/v1`.
- [`plan-adapter.yaml`](.acdd/plan-adapter.yaml) owns bounded planning
  verification and terminal planning-set review.

There is no detached reviewer role. Copy the adapter for the domain role that
owns the gate, then replace authority, launcher, model, and tool-envelope values
with tools exposed by that host.

`code_map_query` alone satisfies the dependency-impact capability when invoked
with `operation=impact`. Use `profile` to select the review risk lens, `view` to
bound response detail, and `operation=path` only when the reviewer needs a
specific source-to-destination chain. A truncated result requires a widened
follow-up query before the discovery receipt can be complete.

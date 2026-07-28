# Reviewer adapter examples

These full adapters show the owner-bound review pattern:

- [`task-adapter.yaml`](.acdd/task-adapter.yaml) owns isolated inbound
  `architecture/v1`: four read-only inspectors, then one tool-free coordinator.
- [`implementation-adapter.yaml`](.acdd/implementation-adapter.yaml) owns the
  terminal task `review/v1`.
- [`plan-adapter.yaml`](.acdd/plan-adapter.yaml) owns bounded planning
  verification and terminal planning-set review.

Copy the adapter for the domain role that runs the gate. Replace authority,
launcher, model, and tool-envelope values with those exposed by that host.

For G1 amendments, declare an adapter-owned `architectureArtifacts` backend.
It records the frozen manifest, receipt, and paired transcript outside task
Markdown, using host-selected storage, retention, redaction, and serialization.

`code_map_query` alone satisfies the dependency-impact capability when invoked
with `operation=impact`. Use `profile` to select the review risk lens, `view` to
bound response detail, and `operation=path` only when the reviewer needs a
specific source-to-destination chain. A truncated result requires a widened
follow-up query before the discovery receipt can be complete.

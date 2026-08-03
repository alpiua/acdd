# ACDD examples

Copy the smallest bundle that matches the owning domain. Replace every example
authority, path, command, model, tool, and external mapping with live owner
values.

| Example | Use it for | Includes |
|---|---|---|
| [`planner/.acdd-legacy/`](planner/.acdd-legacy/) | Filesystem roadmap delivery | Task and plan adapters, impact variants, task lifecycle rules |
| [`codebase/.acdd-legacy/`](codebase/.acdd-legacy/) | Code/test/configuration owner | Full and light implementation adapters, release invariants |
| [`reviewers/`](reviewers/) | Independent architecture and closure review | Task, implementation, and plan gate ownership with real launchers |
| [`simple-plan/`](simple-plan/) | Self-contained milestone planning | Runnable plan, adapter, contract, and reference bundle |
| [`linear/.acdd-legacy/`](linear/.acdd-legacy/) | Linear projection | Initiative → Project → Project Milestone → Issue mapping |
| [`jira/.acdd-legacy/`](jira/.acdd-legacy/) | Jira projection | Initiative → Epic → Version/Release → Story or Task mapping |
| [`audit/.acdd-legacy/`](audit/.acdd-legacy/) | Terminal report publication | Audit adapter for selected code or plan review reports |
| [`task/TASK.md`](task/TASK.md) | Full bound task document | Typed inputs, decisions, evidence, and pending receipts |
| [`task/workflow-learning.yaml`](task/workflow-learning.yaml) | Post-review reflection record | Missed-invariant analysis and a prospective canonical guidance candidate |
| [`task-light/TASK.md`](task-light/TASK.md) | Reduced-scope task document | Light typed inputs and evidence shape |

Plans stay separately bound artifacts. Select impact axes in the owner adapter:
the bundles demonstrate software-delivery, data-platform, regulated-service,
product/customer, and commercial variants.

Reviewer bundles are full owner adapters. Their task adapter launches the
four-partition architecture review; implementation and plan adapters launch the
terminal review they own. `code_map_query(operation=impact)` supplies
dependency-impact evidence when that tool is available.

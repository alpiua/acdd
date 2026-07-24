# Adapter examples

| Domain | Adapters | Projection |
|---|---|---|
| [`linear/.acdd/`](linear/.acdd/) | plan | Initiative → Project → Project Milestone → Issue |
| [`jira/.acdd/`](jira/.acdd/) | plan | Initiative → Epic → Version/Release → Story or Task |
| [`planner/.acdd/`](planner/.acdd/) | task, plan | filesystem roadmap, phases, milestones, tasks, and plans |
| [`codebase/.acdd/`](codebase/.acdd/) | implementation | source, tests, configuration, docs, gates, code review |
| [`reviewers/`](reviewers/) | task, implementation, plan | Planner-style inbound architecture and terminal overview review |
| [`audit/.acdd/`](audit/.acdd/) | audit | selected terminal report publication |
| [`simple-plan/`](simple-plan/) | plan | self-contained milestone plan with embedded tasks |
| [`task/TASK.md`](task/TASK.md) | task document | inline typed inputs, evidence, and pending receipts |
| [repository `.acdd/`](../.acdd/) | plan | this package's own simple-plan adapter |

Copy the matching `.acdd/` directory into the repository that owns the domain,
then replace example authority and procedures with live paths and commands.

Plans remain separately bound artifacts. Impact axes come from the selected
adapter; the examples include software-delivery, data-platform, regulated,
product/customer, and commercial variants.

The reviewer examples are full owner adapters, not a detached reviewer role.
They show command-launched inbound verification, tool-launched terminal review,
and a single `code_map_query(operation=impact)` binding for reverse dependency
evidence.

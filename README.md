# ACDD Workflow

Host-neutral contracts for two explicit flows:

- [`acdd/task/v1`](profiles/task/v1.yaml) delivers one bound implementation task.
- [`acdd/plan/v1`](profiles/plan/v1.yaml) creates or improves one bounded planning set.

The planning hierarchy is `roadmap → phases → milestones → tasks`. Plans are
separate artifacts bound to one roadmap, phase, milestone, or task and may span
phases. [`acdd/plan/simple/v1`](contracts/plan/simple/v1.yaml) provides a
self-contained milestone plan with embedded tasks.

Profiles define ordered gates and terminal receipt semantics. Owner adapters
define authority, impact axes, review runtime, and repository procedures.

## Runtime composition

Task:

```bash
python3 scripts/validate_acdd.py \
  --profile profiles/task/v1.yaml \
  --workspace-root . \
  --document examples/task/TASK.md \
  --adapter task=examples/planner/.acdd/task-adapter.yaml \
  --adapter implementation=examples/codebase/.acdd/implementation-adapter.yaml
```

Plan:

```bash
python3 scripts/validate_acdd.py \
  --profile profiles/plan/v1.yaml \
  --workspace-root . \
  --document PLAN.md \
  --adapter plan=examples/planner/.acdd/plan-adapter.yaml
```

The routing contract selects one executor adapter per queued gate. The task adapter
owns task state, impact, and task `architecture/v1` execution; the implementation
adapter contributes architecture authority and capabilities, executes repository gates,
and owns final task `review/v1`. The plan adapter executes the planning flow. The
optional audit adapter publishes selected terminal reports. Architecture verification
uses the generic [four-partition schema](contracts/architecture-verification/v1.yaml)
and an owner-supplied concrete contract.

In the ContextUnity multi-repository workspace, substitute the owner bundles at
`../../planner/.acdd/`, `../../contextunity/.acdd/`, and
`../../audit/.acdd/`, set `--workspace-root ../..`, and supply only the roles
used by that flow.

See [`INSTALL.md`](INSTALL.md) and the [domain examples](examples/README.md).

Validate package-local links with:

```bash
python3 scripts/check_markdown_links.py --root .
```

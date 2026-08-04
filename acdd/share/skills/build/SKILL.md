---
name: acdd-v2-build
description: Run the build/v1 ACDD gate.
---

# build/v1

## Load

Read the integrated workspace, profile, and implementation adapter. Load the
mandatory [TDD procedure](../tdd/SKILL.md), then `runtime-and-integration`;
append its `promptAppend` fragment if present.

## TDD

The frozen Contract gives every subtask its behavior, acceptance, and forbidden
effects. Its separately hashed source-contract part and matching binding are
immutable during Build; both live in one append-only bundle. Register new work
before testing it: additive non-overlapping slices via `contract-subtask` (+
re-verify); material `supersedes` / overlapping writes / `*repair*` ids via
`reopen` + Contract re-finalize (see Contract skill). Build expresses each
subtask's scope in a focused functional test at the canonical behavior
boundary; a test for one subtask cannot prove another subtask's acceptance.
`acdd record` on Build requires `--changed` and/or a git worktree; dirty
Input paths outside active subtask writes fail.

**Subagents (preferred):** After `contract/v1` finalize, follow the
`contract-verify` Delivery command. Launch **one separate subagent per
subtask** in each parallel wave (one subagent ↔ one subtask). Do not fold
independent wave-mates into a single agent session. If the host cannot spawn
subagents, isolate the same way manually: one subtask's Red→Green at a time
within a wave, never mixing scopes. Respect `dependsOn` / `supersedes` before
admitting a subtask to the next wave.

**Red** is that test failing before its production change because the intended
behavior is absent or wrong. An import failure, test setup error, configuration
failure, or mock interaction alone is not Red evidence. **Green** is the same
test passing after the smallest fitting production change, before broader
verification.

## runtime-and-integration

After the focused TDD test is green, run the owner-bound command on the
integrated tree. It must prove the intended runtime behavior and
integration/repository-quality contract together. A timeout or non-zero result
is not a pass.

Tune the binding, not the run: `timeoutSeconds` (default 300) sets the proof
budget for this repository, and `promptAppend` adds repository context. Both
are declared in the implementation adapter and hashed into the gate
fingerprint, so changing them re-opens the gate.

## Evidence

Record the command artifact and finalize only when its fingerprint is current.
Use gate-level `inapplicable` only with a declared profile reason and no check
evidence.

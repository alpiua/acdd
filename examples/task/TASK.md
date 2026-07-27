---
title: "Example bounded implementation task"
status: todo
delivery_profile: acdd/task/v1
---

# Example bounded implementation task

## Objective

Prove `task.example` through one declared source and `proof.example-red`.

## Coverage analysis (ACDD)

`decision.example-coverage` maps the current caller and owner.

## Architecture coherence & blast radius (G0)

The example uses one canonical owner and no alternate writer.

## Task execution contract (G0 output)

`contract.example` binds the input, owner, result, and failure behavior.

## G0 architecture baseline

### Outcome and ownership

`decision.example-coverage` selects one canonical owner and no alternate writer.

### Contract and propagation

`contract.example` binds input, owner, result, and failure behavior through
`trigger → caller → contract.example → owner → result`.

### Authority, lifecycle, and proof

`authority.example` and `lifecycle.example` are closed by
`proof.example-red`, `proof.example-scope`, and `proof.example-parity`.

## Contract propagation matrix

`contract.example` → `proof.example-red`.

## Authority and identity matrix

`authority.example` → `proof.example-scope`.

## Lifecycle and alternate-path matrix

`lifecycle.example` → `proof.example-parity`.

## G0 completeness barrier

All example decisions and proofs must resolve before implementation.

## G0 decision registry

- [ ] `decision.example-coverage` — unresolved; proof=`proof.example-red`

## Execution gates

- [ ] G0 architecture
- [ ] G1 runtime
- [ ] G2 security
- [ ] G3 release

## Runtime path (required)

`trigger → caller → contract.example → owner → result`

## Surfaces

The example exposes no external effect.

## Config surface

No configuration field is added.

## Out of scope

- Product implementation.

## Handoff / blockers

- Pending example execution.

## G1 redesign amendments

```yaml
apiVersion: acdd/architecture-amendments/v2
kind: architecture-amendments
items: []
```

## ACDD inputs

```yaml
apiVersion: acdd/inputs/v1
kind: inputs
paths:
  - type: source
    path: README.md
```

## ACDD gate evidence

```yaml
[]
```

## ACDD receipts

| Gate | Status | Evidence / receipt | Input fingerprint | Recorded UTC |
|---|---|---|---|---|
| `matrix/v1` | `pending` | pending | `pending` | `pending` |
| `architecture/v1` | `pending` | pending | `pending` | `pending` |
| `red/v1` | `pending` | pending | `pending` | `pending` |
| `runtime/v1` | `pending` | pending | `pending` | `pending` |
| `parity/v1` | `pending` | pending | `pending` | `pending` |
| `security/v1` | `pending` | pending | `pending` | `pending` |
| `release/v1` | `pending` | pending | `pending` | `pending` |
| `review/v1` | `pending` | pending | `pending` | `pending` |
| `handoff/v1` | `pending` | pending | `pending` | `pending` |

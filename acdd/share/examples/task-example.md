---
title: Fix resource leak in pool module
planning_profile: acdd/task/v1
executable_proof:
  argv: [uv, run, pytest, tests/test_pool.py::test_expired_jobs_release, -q]
  expected_failure: "assert"
---

## Plan

```yaml
subtasks:
  - id: pool-release
    writes: [src/pool.py, tests/test_pool.py]
    reads: [src/contracts.py]
    acceptance: expired jobs are released and round-trip ordering is preserved
    dependsOn: []
```

## Inputs

```yaml
paths:
  - {type: source, path: src/pool.py}
  - {type: test, path: tests/test_pool.py}
  - {type: configuration, path: config/pool.yaml}
  - {type: structure, path: src/contracts.py}
```

## Evidence

## Receipts

| gate | status | evidence | fingerprint | recordedAt |
| --- | --- | --- | --- | --- |
| design/v1 | pending | pending | pending | pending |
| contract/v1 | pending | pending | pending | pending |
| build/v1 | pending | pending | pending | pending |
| review/v1 | pending | pending | pending | pending |
| handoff/v1 | pending | pending | pending | pending |

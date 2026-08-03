---
title: Fix memory leak in worker pool
planning_profile: acdd/task/v1
executable_proof:
  argv: [uv, run, pytest, tests/worker/test_pool.py::test_expired_jobs_release, -q]
  expected_failure: "assert"
---

## Plan

```yaml
subtasks:
  - id: worker-pool
    writes: [services/worker/pool.py, tests/worker/test_pool.py]
    reads: [packages/contracts/worker.py]
    acceptance: expired jobs are released and round-trip ordering is preserved
    dependsOn: []
```

## Inputs

```yaml
paths:
  - {type: source, path: services/worker/pool.py}
  - {type: test, path: tests/worker/test_pool.py}
  - {type: configuration, path: services/worker/config.yaml}
  - {type: structure, path: packages/contracts/worker.py}
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

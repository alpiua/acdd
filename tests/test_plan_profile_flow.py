"""Planning-profile lifecycle regression."""

from __future__ import annotations

import json
from pathlib import Path

from acdd.cli import main


def test_standard_plan_profile_completes_all_three_gates(tmp_path: Path, ROOT: Path):
    profile = ROOT / "profiles" / "plan" / "v1.yaml"
    (tmp_path / "planning.md").write_text("bounded planning set\n", encoding="utf-8")
    document = tmp_path / "plan.md"
    document.write_text(
        """\
---
title: Standard planning profile
planning_profile: acdd/plan/v1
---
## Plan
```yaml
subtasks:
  - id: planning-slice
    writes: [planning.md]
    reads: []
    acceptance: planning set is complete and consistent
    dependsOn: []
```
## Inputs
```yaml
paths: [{type: structure, path: planning.md}]
```
## Evidence

## Receipts
| gate | status | evidence | fingerprint | recordedAt |
| --- | --- | --- | --- | --- |
| design/v1 | pending | pending | pending | pending |
| decompose/v1 | pending | pending | pending | pending |
| review/v1 | pending | pending | pending | pending |
""",
        encoding="utf-8",
    )
    adapters = tmp_path / ".acdd"
    adapters.mkdir()
    (adapters / "plan.yaml").write_text(
        """\
apiVersion: acdd/adapter/v1
id: plan
role: plan
gates:
  design/v1:
    checks:
      design-basis: {argv: [/bin/true]}
      plan-shape: {argv: [/bin/true]}
  decompose/v1:
    checks:
      decomposition: {argv: [/bin/true]}
      matrix: {argv: [/bin/true]}
""",
        encoding="utf-8",
    )
    (adapters / "review.yaml").write_text(
        """\
apiVersion: acdd/adapter/v1
id: review
role: review
gates:
  review/v1:
    checks:
      independent-review: {argv: [/bin/true]}
""",
        encoding="utf-8",
    )

    def run(command: str, *args: str) -> None:
        assert (
            main([command, str(document), str(profile), "--workspace-root", str(tmp_path), *args])
            == 0
        )

    for gate, check in (
        ("design/v1", "design-basis"),
        ("design/v1", "plan-shape"),
        ("decompose/v1", "decomposition"),
        ("decompose/v1", "matrix"),
    ):
        flags = (
            ("--classified-ref", "planning.md=plan")
            if check in {"design-basis", "decomposition", "matrix"}
            else ()
        )
        run("record", "--gate", gate, "--check", check, "--id", gate[:3] + "." + check, *flags)
        if check == "plan-shape":
            run("finalize", "--gate", gate, "--id", "design.bundle")
        if check == "matrix":
            run("finalize", "--gate", gate, "--id", "decompose.bundle")
    transcript = adapters / "artifacts" / "review.jsonl"
    transcript.parent.mkdir(exist_ok=True)
    transcript.write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                {
                    "type": "review_raw",
                    "reviewerSessionUuid": "00000000-0000-4000-8000-000000000002",
                    "raw": "complete",
                },
                {
                    "type": "review_terminal",
                    "evidenceId": "review.independent",
                    "gate": "review/v1",
                    "check": "independent-review",
                    "scope": ["planning.md"],
                    "performedChecks": ["completeness", "consistency"],
                    "verdict": "pass",
                    "authorSessionUuid": "00000000-0000-4000-8000-000000000001",
                    "reviewerSessionUuid": "00000000-0000-4000-8000-000000000002",
                    "reviewedSessionUuids": ["00000000-0000-4000-8000-000000000002"],
                },
            )
        )
        + "\n",
        encoding="utf-8",
    )
    run(
        "review",
        "--gate",
        "review/v1",
        "--check",
        "independent-review",
        "--id",
        "review.independent",
        "--transcript",
        ".acdd/artifacts/review.jsonl",
        "--author-uuid",
        "00000000-0000-4000-8000-000000000001",
        "--reviewer-uuid",
        "00000000-0000-4000-8000-000000000002",
    )
    run("finalize", "--gate", "review/v1", "--id", "review.bundle")
    run("validate")

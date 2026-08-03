"""Full standard task-profile lifecycle regression."""

from __future__ import annotations

import json
from pathlib import Path

from acdd.cli import main


def test_standard_task_profile_completes_all_five_gates(tmp_path: Path, ROOT: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_value(): assert True\n", encoding="utf-8"
    )
    (tmp_path / "design.md").write_text("bounded task\n", encoding="utf-8")
    profile = ROOT / "profiles" / "task" / "v1.yaml"
    document = tmp_path / "task.md"
    document.write_text(
        """\
---
title: Standard task profile
planning_profile: acdd/task/v1
---
## Plan
```yaml
subtasks:
  - id: change
    writes: [src/app.py, tests/test_app.py]
    reads: [design.md]
    acceptance: the bounded behavior is proved
    dependsOn: []
```
## Inputs
```yaml
paths:
  - {type: structure, path: design.md}
  - {type: source, path: src/app.py}
  - {type: test, path: tests/test_app.py}
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
""",
        encoding="utf-8",
    )
    adapters = tmp_path / ".acdd"
    adapters.mkdir()
    (adapters / "task.yaml").write_text(
        """\
apiVersion: acdd/adapter/v1
id: task
role: task
gates:
  design/v1:
    checks:
      design-basis: {argv: [/bin/true]}
      plan-shape: {argv: [/bin/true]}
  contract/v1:
    checks:
      decomposition: {argv: [/bin/true]}
      executable-proof: {argv: [python3, -c, "import sys; sys.exit(1)"]}
  handoff/v1:
    checks:
      repository-handoff: {argv: [/bin/true]}
""",
        encoding="utf-8",
    )
    (adapters / "contract-verify.yaml").write_text(
        """\
apiVersion: acdd/adapter/v1
id: contract-verify
role: contract-verify
gates:
  contract/v1:
    checks:
      contract-verify: {argv: [/bin/true]}
""",
        encoding="utf-8",
    )
    (adapters / "implementation.yaml").write_text(
        """\
apiVersion: acdd/adapter/v1
id: implementation
role: implementation
gates:
  build/v1:
    checks:
      runtime-and-integration: {argv: [/bin/true]}
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

    run(
        "record",
        "--gate",
        "design/v1",
        "--check",
        "design-basis",
        "--id",
        "des.design-basis",
        "--classified-ref",
        "design.md=task",
    )
    run("record", "--gate", "design/v1", "--check", "plan-shape", "--id", "des.plan-shape")
    run("finalize", "--gate", "design/v1", "--id", "design.bundle")
    run(
        "record",
        "--gate",
        "contract/v1",
        "--check",
        "decomposition",
        "--id",
        "con.decomposition",
        "--classified-ref",
        "design.md=task",
    )
    run(
        "record",
        "--gate",
        "contract/v1",
        "--check",
        "executable-proof",
        "--id",
        "contract.proof",
    )
    verify_transcript = adapters / "artifacts" / "contract-verify.jsonl"
    verify_transcript.parent.mkdir(exist_ok=True)
    verify_transcript.write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                {
                    "type": "review_raw",
                    "reviewerSessionUuid": "00000000-0000-4000-8000-000000000012",
                    "raw": "permission granted; no open fixes",
                },
                {
                    "type": "review_terminal",
                    "evidenceId": "contract.verify",
                    "gate": "contract/v1",
                    "check": "contract-verify",
                    "scope": ["design.md"],
                    "performedChecks": [
                        "completeness",
                        "chain-coverage",
                        "proof-strength",
                        "parallel-safety",
                    ],
                    "verdict": "pass",
                    "authorSessionUuid": "00000000-0000-4000-8000-000000000011",
                    "reviewerSessionUuid": "00000000-0000-4000-8000-000000000012",
                    "reviewedSessionUuids": ["00000000-0000-4000-8000-000000000012"],
                },
            )
        )
        + "\n",
        encoding="utf-8",
    )
    run(
        "review",
        "--gate",
        "contract/v1",
        "--check",
        "contract-verify",
        "--id",
        "contract.verify",
        "--transcript",
        ".acdd/artifacts/contract-verify.jsonl",
        "--author-uuid",
        "00000000-0000-4000-8000-000000000011",
        "--reviewer-uuid",
        "00000000-0000-4000-8000-000000000012",
    )
    run("finalize", "--gate", "contract/v1", "--id", "contract.bundle")
    run(
        "record",
        "--gate",
        "build/v1",
        "--check",
        "runtime-and-integration",
        "--id",
        "build.runtime",
    )
    run("finalize", "--gate", "build/v1", "--id", "build.bundle")
    transcript = adapters / "artifacts" / "review.jsonl"
    transcript.write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                {
                    "type": "review_raw",
                    "reviewerSessionUuid": "00000000-0000-4000-8000-000000000002",
                    "raw": '{"findings": []}',
                },
                {
                    "type": "review_terminal",
                    "evidenceId": "review.independent",
                    "gate": "review/v1",
                    "check": "independent-review",
                    "scope": ["src/app.py"],
                    "performedChecks": ["parity", "security", "code"],
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
    run(
        "record",
        "--gate",
        "handoff/v1",
        "--check",
        "repository-handoff",
        "--id",
        "handoff.repository",
    )
    run("finalize", "--gate", "handoff/v1", "--id", "handoff.bundle")
    text = document.read_text(encoding="utf-8")
    assert "processReportRef:" in text
    report = next(Path(tmp_path).joinpath(".acdd/artifacts").glob("*.process-report.json"))
    assert json.loads(report.read_text(encoding="utf-8"))["format"] == "acdd/process-report/1"
    run("validate")

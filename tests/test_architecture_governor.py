from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str) -> object:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GOV = _load("architecture_governor")
ARCH = _load("architecture_verification")
RUNNER = _load("run_architecture")
SCHEMA = ARCH.load_yaml(ROOT / "contracts" / "architecture-verification" / "v1.yaml")


def _discovery() -> dict[str, object]:
    capabilities = {
        "exactText": "source_map",
        "structural": "structural_search",
        "dependency": "impact",
    }
    return {
        "repositoryRoot": ".",
        "methods": {
            name: {
                "capability": capability,
                "tools": ["mcp"],
                "queries": [f"{name} query"],
                "complete": True,
            }
            for name, capability in capabilities.items()
        },
    }


def _candidate_finding(
    ident: str = "candidate-gap",
    *,
    task_path: str = "task.md",
    code_path: str = "services/callers.py",
) -> dict[str, object]:
    return {
        "id": ident,
        "defectKind": "incomplete-propagation",
        "candidateDefect": "The frozen task omits a required production path.",
        "taskEvidence": [f"{task_path}:1"],
        "codeEvidence": [f"{code_path}:1"],
        "requiredTaskChange": "Add the missing path, owner, and acceptance proof.",
    }


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def test_baseline_clean_declared_inputs_pass() -> None:
    GOV.validate_baseline(
        dirty_paths=("notes.md",),
        declared_implementation_paths=frozenset({"source.py", "test.py"}),
        candidate_set=(),
    )


def test_baseline_dirty_declared_without_candidate_fails() -> None:
    with pytest.raises(GOV.ArchitectureGovernorError, match="candidate-set coverage"):
        GOV.validate_baseline(
            dirty_paths=("source.py", "notes.md"),
            declared_implementation_paths=frozenset({"source.py"}),
            candidate_set=(),
        )


def test_baseline_dirty_declared_covered_by_candidate_passes(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("x", encoding="utf-8")
    candidate = GOV.CandidatePath("source.py", _digest(b"x"))
    GOV.validate_baseline(
        dirty_paths=("source.py",),
        declared_implementation_paths=frozenset({"source.py"}),
        candidate_set=(candidate,),
    )
    GOV.validate_candidate_locks((candidate,), workspace_root=tmp_path)


def test_candidate_stale_lock_fails(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("fresh", encoding="utf-8")
    candidate = GOV.CandidatePath("source.py", _digest(b"stale"))
    with pytest.raises(GOV.ArchitectureGovernorError, match="stale lock"):
        GOV.validate_candidate_locks((candidate,), workspace_root=tmp_path)


def test_unchanged_fail_rerun_forbidden() -> None:
    fp = "sha256:" + "a" * 64
    attempts = (
        GOV.ArchitectureAttempt(fp, "FAIL", "2026-07-24T00:00:00Z"),
    )
    with pytest.raises(GOV.ArchitectureGovernorError, match="unchanged FAIL"):
        GOV.validate_retry_admission(attempts, next_fingerprint=fp)
    # compatibility with existing helper
    failed = {
        "inputFingerprint": fp,
        "coordinator": {"verdict": "FAIL"},
    }
    with pytest.raises(ARCH.ArchitectureVerificationError, match="unchanged FAIL"):
        ARCH.validate_retry_fingerprint(failed, fp)


def test_material_attempt_cap() -> None:
    attempts = (
        GOV.ArchitectureAttempt("sha256:" + "1" * 64, "FAIL", "2026-07-24T00:00:00Z"),
        GOV.ArchitectureAttempt("sha256:" + "2" * 64, "FAIL", "2026-07-24T00:00:00Z"),
        GOV.ArchitectureAttempt("sha256:" + "3" * 64, "FAIL", "2026-07-24T00:00:00Z"),
    )
    with pytest.raises(GOV.ArchitectureGovernorError, match="attempt cap exceeded"):
        GOV.validate_retry_admission(
            attempts,
            next_fingerprint="sha256:" + "4" * 64,
            max_material_attempts=3,
        )
    # retrying a new fingerprint after only 2 fails is OK
    GOV.validate_retry_admission(
        attempts[:2],
        next_fingerprint="sha256:" + "9" * 64,
        max_material_attempts=3,
    )


def test_parse_admission_defaults_and_section() -> None:
    default = GOV.parse_architecture_admission("# No section\n")
    assert default.max_material_attempts == 3
    assert default.candidate_set == ()
    assert default.attempts == ()

    text = """## ACDD architecture admission

```yaml
apiVersion: acdd/architecture-admission/v1
kind: architecture-admission
maxMaterialAttempts: 2
candidateSet:
  - path: source.py
    sha256: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
attempts:
  - inputFingerprint: sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
    verdict: FAIL
    recordedAt: "2026-07-24T10:00:00Z"
```
"""
    parsed = GOV.parse_architecture_admission(text)
    assert parsed.max_material_attempts == 2
    assert parsed.candidate_set[0].path == "source.py"
    assert parsed.attempts[0].verdict == "FAIL"


def test_may_launch_reports_block_reason(tmp_path: Path) -> None:
    (tmp_path / "source.py").write_text("x", encoding="utf-8")
    text = """## Objective

x

## ACDD inputs

```yaml
apiVersion: acdd/inputs/v1
kind: inputs
paths:
  - type: source
    path: source.py
```
"""
    # Minimal text without full semantic sections - declared paths only via parse_inputs
    # may_launch uses declared_implementation_paths which needs full inputs parse - OK
    ok, reason = GOV.may_launch_architecture(
        text=text,
        workspace_root=tmp_path,
        next_fingerprint="sha256:" + "c" * 64,
        dirty_paths=("source.py",),
    )
    assert ok is False
    assert "candidate-set" in reason


def test_check_architecture_admission_cli(tmp_path: Path) -> None:
    # Build a tiny git repo with clean declared input.
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "source.py").write_text("ok\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.py"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    # Reuse fixture-like adapters/document from proof bundle patterns — minimal doc
    # for fingerprint needs full task semantic sections. Use may_launch unit path instead.
    dirty = GOV.collect_dirty_paths(tmp_path)
    assert dirty == ()

def test_runner_rejects_writable_and_incomplete_partition_output() -> None:
    fingerprint = "sha256:" + "a" * 64
    partition = {
        "id": "contract",
        "status": "pass",
        "inputFingerprint": fingerprint,
        "evidence": ["task.md:1"],
        "findings": [],
        "persistedContractMappings": [],
        "isolated": True,
        "readOnly": True,
        "discovery": _discovery(),
    }
    RUNNER.check_partition(partition, "contract", fingerprint, SCHEMA)
    partition["evidence"] = [{"path": "task.md", "line": 1}]
    with pytest.raises(RUNNER.RunnerError, match="evidence"):
        RUNNER.check_partition(partition, "contract", fingerprint, SCHEMA)
    partition["evidence"] = ["task.md:1"]
    partition["readOnly"] = False
    with pytest.raises(RUNNER.RunnerError, match="read-only"):
        RUNNER.check_partition(partition, "contract", fingerprint, SCHEMA)
    partition["readOnly"] = True
    partition["discovery"]["methods"]["dependency"]["complete"] = False
    with pytest.raises(RUNNER.RunnerError, match="dependency"):
        RUNNER.check_partition(partition, "contract", fingerprint, SCHEMA)


def test_runner_parses_multiline_json_and_ignores_noise() -> None:
    output = """startup warning
```json
{
  "id": "contract",
  "status": "pass"
}
```
"""
    assert RUNNER.parse_launcher_output(output, ("id", "status")) == {
        "id": "contract",
        "status": "pass",
    }


def test_runner_rejects_json_without_required_fields() -> None:
    with pytest.raises(RUNNER.RunnerError, match="required JSON object"):
        RUNNER.parse_launcher_output('{"message": "not a partition"}', ("id", "status"))


def test_runner_aggregates_pi_jsonl_usage() -> None:
    output = "\n".join([
        RUNNER.json.dumps({
            "type": "message_end",
            "message": {
                "role": "assistant",
                "usage": {
                    "input": 10, "output": 4, "cacheRead": 6,
                    "cacheWrite": 2, "cost": {"total": 0.25},
                },
            },
        }),
        RUNNER.json.dumps({
            "type": "message_end",
            "message": {
                "role": "assistant",
                "usage": {
                    "input": 3, "output": 1, "cacheRead": 0,
                    "cacheWrite": 0, "cost": {"total": 0.05},
                },
            },
        }),
    ])
    assert RUNNER.parse_launcher_usage(output) == {
        "available": True,
        "input": 13,
        "output": 5,
        "cacheRead": 6,
        "cacheWrite": 2,
        "cost": 0.3,
        "totalTokens": 26,
    }


def test_runner_normalizes_non_pi_launcher_usage() -> None:
    output = RUNNER.json.dumps({
        "usage": {
            "input_tokens": 8,
            "output_tokens": 3,
            "cache_read_tokens": 2,
            "cache_write_tokens": 1,
            "total_cost": 0.12,
        },
    })
    assert RUNNER.parse_launcher_usage(output) == {
        "available": True,
        "input": 8,
        "output": 3,
        "cacheRead": 2,
        "cacheWrite": 1,
        "cost": 0.12,
        "totalTokens": 14,
    }


def test_partition_cannot_fail_on_current_code_without_task_defect() -> None:
    fingerprint = "sha256:" + "a" * 64
    partition = {
        "id": "callers",
        "status": "fail",
        "inputFingerprint": fingerprint,
        "evidence": ["services/callers.py:1"],
        "findings": [{
            **_candidate_finding(),
            "candidateDefect": "The current code still uses the legacy API.",
            "taskEvidence": [],
        }],
        "discovery": _discovery(),
        "persistedContractMappings": [],
        "isolated": True,
        "readOnly": True,
    }
    with pytest.raises(RUNNER.RunnerError, match="taskEvidence"):
        RUNNER.check_partition(
            partition, "callers", fingerprint, SCHEMA,
            expected_document=Path("task.md"),
        )


def test_runner_retries_only_transport_or_schema_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fingerprint = "sha256:" + "b" * 64
    domains = frozenset({"celledge.endpoint-format"})
    valid = {
        "id": "contract",
        "status": "fail",
        "inputFingerprint": fingerprint,
        "evidence": ["task.md:1"],
        "findings": [_candidate_finding()],
        "discovery": _discovery(),
        "persistedContractMappings": sorted(domains),
        "isolated": True,
        "readOnly": True,
    }
    calls = []

    invalid = {**valid, "persistedContractMappings": ["edges.proof-id"]}

    def fake_launch(*args, **kwargs):
        calls.append(args)
        return invalid if len(calls) == 1 else valid

    monkeypatch.setattr(RUNNER, "launch", fake_launch)
    result = RUNNER.run_inspector(
        "contract", {"id": "contract"}, fingerprint, tmp_path / "task.md",
        tmp_path, {}, SCHEMA, domains,
    )
    assert result["status"] == "fail"
    assert len(calls) == 2
    retry_prompt = RUNNER.json.loads(calls[1][1])
    assert "candidate-gap" in retry_prompt["priorAttemptFailure"]["responseExcerpt"]
    assert retry_prompt["discoveryContract"]["methods"] == {
        name: {"capability": capability}
        for name, capability in RUNNER.DISCOVERY_CAPABILITIES.items()
    }
    assert retry_prompt["persistedContractContract"] == {
        "allowedDomainIds": sorted(domains),
        "coverage": "complete",
        "forbiddenIdKinds": ["proof", "matrix"],
    }
    assert retry_prompt["reviewSubject"]["implementationCompletionIsOutOfScope"] is True
    assert "never by itself a finding" in retry_prompt["findingContract"]["rule"]
    assert "unfinished/legacy" not in retry_prompt["instruction"]

    calls.clear()
    monkeypatch.setattr(
        RUNNER, "launch",
        lambda *args, **kwargs: calls.append(args) or valid,
    )
    result = RUNNER.run_inspector(
        "contract", {"id": "contract"}, fingerprint, tmp_path / "task.md",
        tmp_path, {}, SCHEMA, domains,
    )
    assert result["status"] == "fail"
    assert len(calls) == 1



def test_runner_records_coordinator_recommendation_instead_of_raw_inspector_advice() -> None:
    recommendation = {
        "id": "canonical-owner-1",
        "sourceFindings": ["callers:1", "persistence:1"],
        "invariant": "One canonical contract owns the value.",
        "rootCause": "Validation is duplicated outside the owner.",
        "canonicalOwner": "packages/core contract",
        "requiredChange": "Move enforcement to the canonical owner and propagate it.",
        "propagation": ["callers", "transport", "SQLite", "PostgreSQL"],
        "prohibitedShortcuts": ["caller-local fallback"],
        "acceptanceProof": ["owner test", "backend parity test"],
        "evidence": ["packages/core/value.py:10"],
    }
    findings = RUNNER.task_findings_from_recommendations([recommendation])
    assert findings == [{
        "id": "canonical-owner-1",
        "partition": "coordinator",
        "summary": recommendation["requiredChange"],
        "invariant": recommendation["invariant"],
        "rootCause": recommendation["rootCause"],
        "canonicalOwner": recommendation["canonicalOwner"],
        "propagation": recommendation["propagation"],
        "prohibitedShortcuts": recommendation["prohibitedShortcuts"],
        "acceptanceProof": recommendation["acceptanceProof"],
        "sourceFindings": recommendation["sourceFindings"],
        "evidence": recommendation["evidence"],
    }]



def _coordinator_partitions(fingerprint: str) -> list[dict[str, object]]:
    return [
        {
            "id": partition,
            "status": "fail" if partition == "callers" else "pass",
            "inputFingerprint": fingerprint,
            "evidence": [f"services/{partition}.py:1"],
            "findings": [_candidate_finding()] if partition == "callers" else [],
            "discovery": _discovery(),
            "persistedContractMappings": [],
            "isolated": True,
            "readOnly": True,
        }
        for partition in ("contract", "authority", "callers", "persistence")
    ]


def _coordinator_recommendation() -> dict[str, object]:
    return {
        "id": "owner-1",
        "sourceFindings": ["callers:1"],
        "invariant": "One canonical contract.",
        "rootCause": "Caller owns validation.",
        "canonicalOwner": "packages/core",
        "requiredChange": "Move validation to its owner.",
        "propagation": ["all callers"],
        "prohibitedShortcuts": ["caller fallback"],
        "acceptanceProof": ["caller parity test"],
        "evidence": ["services/callers.py:1"],
    }


def test_coordinator_schema_retry_preserves_findings_without_rerunning_inspectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fingerprint = "sha256:" + "c" * 64
    partitions = _coordinator_partitions(fingerprint)
    recommendation = _coordinator_recommendation()
    invalid = {"coordinator": {"verdict": "FAIL", "resolvedFindings": [], "reconciledRecommendations": [{**recommendation, "propagation": "all callers"}]}}
    valid = {"coordinator": {"verdict": "FAIL", "resolvedFindings": [], "reconciledRecommendations": [recommendation]}}
    calls = []
    monkeypatch.setattr(RUNNER, "launch", lambda *args, **kwargs: calls.append(args) or (invalid if len(calls) == 1 else valid))
    contract = ARCH.load_yaml(ROOT / "examples" / "task" / "architecture-verification.yaml")
    result = RUNNER.run_coordinator(partitions, fingerprint, {}, tmp_path, {"runtime": "pi"}, SCHEMA, contract, frozenset())
    assert result["coordinator"]["verdict"] == "FAIL"
    assert len(calls) == 2
    retry_prompt = RUNNER.json.loads(calls[1][1])
    assert "propagation" in retry_prompt["priorAttemptFailure"]["validationError"]
    assert retry_prompt["sourceFindings"][0]["finding"]["id"] == "candidate-gap"
    assert retry_prompt["outputContract"]["recommendationShape"]["propagation"] == ["caller -> canonical owner", "transport/storage/backend propagation"]


def test_coordinator_resolves_legacy_code_finding_against_frozen_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fingerprint = "sha256:" + "c" * 64
    partitions = _coordinator_partitions(fingerprint)
    response = {
        "coordinator": {
            "verdict": "PASS",
            "resolvedFindings": ["callers:1"],
            "reconciledRecommendations": [],
        },
    }
    calls = []
    monkeypatch.setattr(
        RUNNER, "launch",
        lambda *args, **kwargs: calls.append(args) or response,
    )
    contract = ARCH.load_yaml(ROOT / "examples" / "task" / "architecture-verification.yaml")
    result = RUNNER.run_coordinator(
        partitions, fingerprint, {}, tmp_path, {"runtime": "pi"}, SCHEMA,
        contract, frozenset(),
        candidate_authority={"Task execution contract (G0 output)": "Legacy API must be removed."},
    )
    assert result["coordinator"]["verdict"] == "PASS"
    prompt = RUNNER.json.loads(calls[0][1])
    assert "Legacy API must be removed." in prompt["candidateAuthority"].values()
    assert "not-yet-implemented code is not a candidate defect" in prompt["recommendationPolicy"]["resolution"]


def test_exhausted_coordinator_preserves_unreconciled_partition_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fingerprint = "sha256:" + "d" * 64
    partitions = _coordinator_partitions(fingerprint)
    invalid = {"coordinator": {"verdict": "FAIL", "resolvedFindings": [], "reconciledRecommendations": [{**_coordinator_recommendation(), "propagation": []}]}}
    monkeypatch.setattr(RUNNER, "launch", lambda *args, **kwargs: invalid)
    contract = ARCH.load_yaml(ROOT / "examples" / "task" / "architecture-verification.yaml")
    with pytest.raises(RUNNER.RunnerError) as raised:
        RUNNER.run_coordinator(partitions, fingerprint, {}, tmp_path, {"runtime": "pi"}, SCHEMA, contract, frozenset(), max_attempts=1)
    assert raised.value.partitions == partitions
    assert raised.value.findings[0] == {"id": "callers:1", "partition": "callers", "summary": "The frozen task omits a required production path.", "finding": partitions[2]["findings"][0], "status": "unreconciled", "evidence": ["services/callers.py:1"]}
    assert raised.value.findings[-1]["id"] == "coordinator:schema"
    assert raised.value.findings[-1]["status"] == "schema-blocked"
    assert "propagation" in raised.value.findings[-1]["rawResponse"]


def test_inspector_wave_preserves_valid_outputs_when_one_partition_exhausts() -> None:
    fingerprint = "sha256:" + "e" * 64
    names = ("contract", "authority", "callers", "persistence")
    completed = []

    def run_one(name: str) -> dict[str, object]:
        completed.append(name)
        if name == "authority":
            invalid = {
                "id": name,
                "status": "fail",
                "findings": [_candidate_finding("authority-gap")],
                "evidence": [{"path": "task.md", "line": 1}],
            }
            raise RUNNER.RunnerError(
                "partition authority.evidence items must use path:line strings",
                retry_payload={
                    "validationError": "partition authority.evidence items must use path:line strings",
                    "responseExcerpt": RUNNER.json.dumps(invalid),
                },
            )
        return {
            "id": name,
            "status": "fail",
            "inputFingerprint": fingerprint,
            "evidence": [f"services/{name}.py:1"],
            "findings": [_candidate_finding(f"{name}-gap", code_path=f"services/{name}.py")],
            "discovery": _discovery(),
            "persistedContractMappings": [],
            "isolated": True,
            "readOnly": True,
        }

    with pytest.raises(RUNNER.RunnerError) as raised:
        RUNNER.collect_inspector_wave(names, run_one, 4)

    assert set(completed) == set(names)
    assert [item["id"] for item in raised.value.partitions] == [
        "contract",
        "callers",
        "persistence",
    ]
    summaries = [item["summary"] for item in raised.value.findings]
    assert summaries == [
        "The frozen task omits a required production path.",
        "The frozen task omits a required production path.",
        "The frozen task omits a required production path.",
        "The frozen task omits a required production path.",
    ]
    assert raised.value.findings[-1]["status"] == "unreconciled-schema"
    assert "path:line strings" in raised.value.findings[-1]["validationError"]
    assert raised.value.findings[-1]["finding"]["id"] == "authority-gap"


def test_schema_blocked_plain_fail_response_is_preserved() -> None:
    error = RUNNER.RunnerError(
        "launcher did not return the required JSON object",
        retry_payload="FAIL: frozen task omits the canonical persistence owner",
    )
    findings = RUNNER.schema_failed_partition_findings("authority", error)
    assert findings == [
        {
            "id": "authority:schema",
            "partition": "authority",
            "summary": "launcher did not return the required JSON object",
            "status": "schema-blocked",
            "validationError": "launcher did not return the required JSON object",
            "rawResponse": '"FAIL: frozen task omits the canonical persistence owner"',
            "containsFail": True,
            "evidence": [],
        }
    ]


def test_record_attempt_preserves_existing_attempt_details(tmp_path: Path) -> None:
    document = tmp_path / "task.md"
    document.write_text("""## ACDD architecture admission

```yaml
apiVersion: acdd/architecture-admission/v1
kind: architecture-admission
maxMaterialAttempts: 3
candidateSet: []
attempts:
  - inputFingerprint: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    verdict: BLOCKED
    recordedAt: '2026-07-26T00:00:00Z'
    findings:
      - id: retained
        partition: callers
        summary: retained raw finding
        evidence: [services/callers.py:1]
```
""", encoding="utf-8")
    usage = {
        "launches": [],
        "totals": {
            "input": 0, "output": 0, "cacheRead": 0,
            "cacheWrite": 0, "cost": 0, "totalTokens": 0,
        },
    }
    RUNNER.record_attempt(
        document, "sha256:" + "b" * 64, "BLOCKED", None, [], [], usage,
    )
    text = document.read_text(encoding="utf-8")
    assert "summary: retained raw finding" in text
    assert text.count("verdict: BLOCKED") == 2
    assert "totalTokens: 0" in text

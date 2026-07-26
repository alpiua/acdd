from __future__ import annotations

import hashlib
import importlib.util
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


FP = _load("acdd_fingerprint")
DOC = _load("acdd_document")
VALIDATOR = _load("validate_acdd")
VALUE_DOMAINS = _load("value_domains")


def _task_text(paths: list[tuple[str, str]]) -> str:
    path_yaml = "\n".join(
        f"  - type: {kind}\n    path: {path}" for kind, path in paths
    )
    semantic_sections = "\n\n".join(
        f"## {name}\n\ncontract.proof — decision.one proof.red-one"
        for name in FP.TASK_SEMANTIC_SECTIONS
    )
    rows = "\n".join(
        f"| `{gate}` | `pending` | pending | `pending` | `pending` |"
        for gate in (
            "matrix/v1",
            "architecture/v1",
            "red/v1",
            "runtime/v1",
            "parity/v1",
            "security/v1",
            "release/v1",
            "review/v1",
            "handoff/v1",
        )
    )
    return f"""---
title: fixture
status: todo
delivery_profile: acdd/task/v1
---

# Fixture

{semantic_sections}

## ACDD inputs

```yaml
apiVersion: acdd/inputs/v1
kind: inputs
paths:
{path_yaml}
```

## ACDD gate evidence

```yaml
[]
```

## ACDD receipts

| Gate | Status | Evidence / receipt | Input fingerprint | Recorded UTC |
|---|---|---|---|---|
{rows}
"""


def _fixture(tmp_path: Path) -> tuple[Path, tuple[Path, ...]]:
    for name in ("source.py", "test.py", "config.yaml", "generated.py", "dep.txt", "env.txt", "findings.txt"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    document = tmp_path / "task.md"
    document.write_text(
        _task_text(
            [
                ("source", "source.py"),
                ("test", "test.py"),
                ("configuration", "config.yaml"),
                ("generated", "generated.py"),
                ("dependency", "dep.txt"),
                ("environment", "env.txt"),
                ("accepted-review-findings", "findings.txt"),
            ]
        ),
        encoding="utf-8",
    )
    task_adapter = tmp_path / "task-adapter.yaml"
    task_adapter.write_text(
        """apiVersion: acdd/adapter/v1
kind: adapter
id: fixture-task/v1
role: task
provides: [task_read, task_write, impact]
procedure: [read]
authority:
  impact:
    domains: [deployment]
constraints: [bounded]
inputAuthorities:
  bound-document: [task.md]
  dependency: ["*"]
  environment: ["*"]
  accepted-review-findings: ["*"]
""",
        encoding="utf-8",
    )
    implementation = tmp_path / "implementation-adapter.yaml"
    implementation.write_text(
        """apiVersion: acdd/adapter/v1
kind: adapter
id: fixture-implementation/v1
role: implementation
provides: [source_map, docs_search, structural_search, run_gate, independent_review, review_execution]
procedure: [inspect]
authority: {source: fixture}
constraints: [bounded]
gateProcedures:
  architecture/v1: {verifier: isolated}
  review/v1: {reviewer: isolated}
inputAuthorities:
  source: ["*"]
  test: ["*"]
  configuration: ["*"]
  generated: ["*"]
  dependency: ["*"]
  environment: ["*"]
  accepted-review-findings: ["*"]
""",
        encoding="utf-8",
    )
    return document, (task_adapter, implementation)


def test_in_memory_fingerprint_is_stable_and_writes_nothing(tmp_path: Path) -> None:
    document, adapters = _fixture(tmp_path)
    result = FP.fingerprint_inputs(
        document=document,
        profile=ROOT / "profiles" / "task" / "v1.yaml",
        receipt_contract=ROOT / "contracts" / "receipt" / "task" / "v1.yaml",
        adapters=adapters,
        workspace_root=tmp_path,
        include_types=frozenset(FP.INPUT_TYPES),
    )
    assert FP.DIGEST_RE.fullmatch(result.sha256)
    assert result.diagnostics == ()
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "config.yaml",
        "dep.txt",
        "env.txt",
        "findings.txt",
        "generated.py",
        "implementation-adapter.yaml",
        "source.py",
        "task-adapter.yaml",
        "task.md",
        "test.py",
    ]


def test_architecture_fingerprint_hashes_only_declared_allowed_code_roots(
    tmp_path: Path,
) -> None:
    code_paths = [
        "contextunity/services/service.py",
        "contextunity/packages/package.py",
        "contextunity/core/core.py",
        "contextunity/extensions/extension.py",
    ]
    ignored_paths = [
        "contextunity/docs/keyword-hit.md",
        "contextunity/.pi-subagents/artifacts/reviewer.md",
        "plugins/acdd-workflow/scripts/run_architecture.py",
    ]
    for relative in (*code_paths, *ignored_paths):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")
    document = tmp_path / "planner" / "task.md"
    document.parent.mkdir(parents=True)
    document.write_text(
        _task_text(
            [("source", path) for path in (*code_paths, *ignored_paths[:2])]
            + [("environment", ignored_paths[2])]
        ),
        encoding="utf-8",
    )
    task_adapter = tmp_path / "planner" / ".acdd" / "task-adapter.yaml"
    task_adapter.parent.mkdir()
    task_adapter.write_text(
        """role: task
inputAuthorities:
  bound-document: [planner/**]
  environment: [plugins/**]
""",
        encoding="utf-8",
    )
    implementation_adapter = (
        tmp_path / "contextunity" / ".acdd" / "implementation-adapter.yaml"
    )
    implementation_adapter.parent.mkdir()
    implementation_adapter.write_text(
        """role: implementation
inputAuthorities:
  source: [contextunity/**]
""",
        encoding="utf-8",
    )
    adapters = (task_adapter, implementation_adapter)
    declared = {item.path for item in FP.parse_inputs(document.read_text(encoding="utf-8"))}
    assert declared == set(code_paths + ignored_paths)

    def code_fingerprint() -> str:
        return FP.fingerprint_architecture_code_inputs(
            document=document,
            adapters=adapters,
            workspace_root=tmp_path,
        ).sha256

    def candidate_fingerprint() -> str:
        return FP.fingerprint_architecture_candidate(
            document=document,
            adapters=adapters,
            workspace_root=tmp_path,
        ).sha256

    baseline = code_fingerprint()
    baseline_candidate = candidate_fingerprint()
    for relative in ignored_paths:
        path = tmp_path / relative
        original = path.read_text(encoding="utf-8")
        path.write_text(original + " changed", encoding="utf-8")
        assert code_fingerprint() == baseline
        assert candidate_fingerprint() == baseline_candidate
        path.write_text(original, encoding="utf-8")
    document.write_text(
        document.read_text(encoding="utf-8").replace("title: fixture", "title: changed"),
        encoding="utf-8",
    )
    assert code_fingerprint() == baseline
    assert candidate_fingerprint() == baseline_candidate
    document.write_text(
        document.read_text(encoding="utf-8")
        + "\n## ACDD architecture admission\n\n```yaml\nattempts: []\n```\n",
        encoding="utf-8",
    )
    assert candidate_fingerprint() == baseline_candidate
    document.write_text(
        document.read_text(encoding="utf-8").replace(
            "## Objective\n\ncontract.proof",
            "## Objective\n\narchitecturally remediated contract.proof",
        ),
        encoding="utf-8",
    )
    assert code_fingerprint() == baseline
    assert candidate_fingerprint() != baseline_candidate
    for relative in code_paths:
        path = tmp_path / relative
        original = path.read_text(encoding="utf-8")
        path.write_text(original + " changed", encoding="utf-8")
        assert code_fingerprint() != baseline
        path.write_text(original, encoding="utf-8")


def test_duplicate_escape_missing_and_authority_fail_closed(tmp_path: Path) -> None:
    document, adapters = _fixture(tmp_path)
    text = document.read_text(encoding="utf-8")
    document.write_text(
        text.replace(
            "  - type: test\n    path: test.py",
            "  - type: test\n    path: source.py",
        ),
        encoding="utf-8",
    )
    with pytest.raises(FP.FingerprintError, match="duplicate input path"):
        FP.parse_inputs(document.read_text(encoding="utf-8"))
    document.write_text(text.replace("source.py", "../source.py", 1), encoding="utf-8")
    with pytest.raises(FP.FingerprintError, match="escapes workspace root"):
        FP.fingerprint_inputs(
            document=document,
            profile=ROOT / "profiles" / "task" / "v1.yaml",
            receipt_contract=ROOT / "contracts" / "receipt" / "task" / "v1.yaml",
            adapters=adapters,
            workspace_root=tmp_path,
            include_types=frozenset(FP.INPUT_TYPES),
        )
    document.write_text(text.replace("source.py", "missing.py", 1), encoding="utf-8")
    with pytest.raises(FP.FingerprintError, match="missing declared input"):
        FP.fingerprint_inputs(
            document=document,
            profile=ROOT / "profiles" / "task" / "v1.yaml",
            receipt_contract=ROOT / "contracts" / "receipt" / "task" / "v1.yaml",
            adapters=adapters,
            workspace_root=tmp_path,
            include_types=frozenset(FP.INPUT_TYPES),
        )


def test_receipt_and_checkbox_changes_do_not_change_semantic_fingerprint(tmp_path: Path) -> None:
    document, _ = _fixture(tmp_path)
    before = FP.semantic_task_fingerprint(document.read_text(encoding="utf-8"))
    changed = (
        document.read_text(encoding="utf-8")
        .replace("| `pending` | pending", "| `blocked` | evidence=x", 1)
        .replace("- [ ]", "- [x]")
    )
    after = FP.semantic_task_fingerprint(changed)
    assert after == before


def test_semantic_contract_and_red_definition_changes_are_detected(tmp_path: Path) -> None:
    document, _ = _fixture(tmp_path)
    before = FP.semantic_task_fingerprint(document.read_text(encoding="utf-8"))
    changed = document.read_text(encoding="utf-8").replace(
        "contract.proof — decision.one proof.red-one",
        "contract.proof — decision.two proof.red-two",
        1,
    )
    after = FP.semantic_task_fingerprint(changed)
    assert after.sha256 != before.sha256
    assert after.red_proof_sha256 != before.red_proof_sha256
    assert set(after.ids) - set(before.ids)


def test_command_output_bound_and_redaction(tmp_path: Path) -> None:
    document, _ = _fixture(tmp_path)
    semantic = FP.semantic_task_fingerprint(document.read_text(encoding="utf-8"))
    digest = "sha256:" + "0" * 64
    lock = "sha256:" + hashlib.sha256((tmp_path / "test.py").read_bytes()).hexdigest()
    evidence = f"""```yaml
apiVersion: acdd/gate-evidence/v1
kind: command
id: red.proof
gate: red/v1
inputFingerprint: {digest}
exactCommand: pytest test.py
recordedAt: "2026-07-23T00:00:00Z"
exitCode: 1
output: "password=visible"
redacted: false
result: expected_failure
expectedException: AssertionError
proofDefinitionFingerprint: {semantic.red_proof_sha256}
componentLocks:
  - path: test.py
    sha256: {lock}
```"""
    text = document.read_text(encoding="utf-8").replace("```yaml\n[]\n```", evidence)
    with pytest.raises(DOC.DocumentError, match="unredacted secret"):
        DOC.parse_evidence(text, workspace_root=tmp_path, semantic=semantic)
    text = text.replace('output: "password=visible"', 'output: "AssertionError: missing behavior"').replace(
        "redacted: false", "redacted: true"
    )
    parsed = DOC.parse_evidence(text, workspace_root=tmp_path, semantic=semantic)
    assert parsed["red.proof"].kind == "command"


def test_every_discriminated_evidence_kind_parses(tmp_path: Path) -> None:
    document, _ = _fixture(tmp_path)
    digest = "sha256:" + "0" * 64
    block = f"""```yaml
apiVersion: acdd/gate-evidence/v1
kind: basis
id: basis.one
gate: matrix/v1
inputFingerprint: {digest}
summary: mapped
authoritySources: [task.md]
mappings: [contract.proof]
contradictions: []
---
apiVersion: acdd/gate-evidence/v1
kind: review
id: review.one
gate: architecture/v1
inputFingerprint: {digest}
adapter: fixture/v1
sessionUuid: 019f8f5f-003b-7374-bcbf-00ff511958b0
authorSessionUuid: 019f86f9-e306-79b5-8007-dda62c0f90a1
reviewer: reviewer
independent: true
terminalVerdict: FAIL
authoritySources: [task.md]
productionPaths: [caller -> owner]
directCallers: [caller]
alternateCallers: []
contradictions: [open]
impactAxes: {{deployment: affected}}
matrixMappings: [contract.proof]
proofMappings: [proof.red-one]
findings: [open]
inventoryComplete: false
decisionsResolved: false
callerCoverageComplete: false
persistedContractChange: false
persistedContractMappings: []
discoveryComplete: false
---
apiVersion: acdd/gate-evidence/v1
kind: handoff
id: handoff.one
gate: handoff/v1
inputFingerprint: {digest}
summary: blocked
receipts: [matrix/v1]
blockers: [architecture]
---
apiVersion: acdd/gate-evidence/v1
kind: rationale
id: rationale.one
gate: red/v1
inputFingerprint: {digest}
rationale: no behavior gap
authorization: bound task
```"""
    text = document.read_text(encoding="utf-8").replace("```yaml\n[]\n```", block)
    parsed = DOC.parse_evidence(
        text,
        workspace_root=tmp_path,
        semantic=FP.semantic_task_fingerprint(text),
    )
    assert {value.kind for value in parsed.values()} == {
        "basis",
        "review",
        "handoff",
        "rationale",
    }


def _value_domain_text(
    tmp_path: Path,
    *,
    strategy: str = "backfill",
    include_reader_disposition: bool = True,
    contract_kind: str = "value-set",
    before_contract: str = "{values: [internal, private, tenant, public]}",
    after_contract: str = "{values: [private, tenant, public]}",
) -> str:
    roles = {
        "producer.py": "producer",
        "writer.py": "writer",
        "schema.sql": "schema",
        "migration.sql": "migration",
        "reader.py": "reader",
        "public_type.py": "public-type",
        "proof.py": "proof",
    }
    domain_root = tmp_path / "services" / "domain"
    domain_root.mkdir(parents=True)
    for name in roles:
        (domain_root / name).write_text(
            f"visibility = {name!r}\n",
            encoding="utf-8",
        )
    generated = domain_root / "node_modules"
    generated.mkdir()
    (generated / "generated.py").write_text(
        "visibility = 'generated dependency'\n",
        encoding="utf-8",
    )
    paths = [("source", f"services/domain/{name}") for name in roles]
    text = _task_text(paths)
    files = "\n".join(
        f"      - path: services/domain/{name}\n        roles: [{role}]"
        for name, role in roles.items()
        if include_reader_disposition or name != "reader.py"
    )
    matrix = f"""## Persisted contract propagation

```yaml
apiVersion: acdd/persisted-contracts/v2
kind: persisted-contracts
domains:
  - id: contract.visibility
    field: visibility
    contractKind: {contract_kind}
    change: changed
    compatibilityImpact: restriction
    beforeContract: {before_contract}
    afterContract: {after_contract}
    discovery:
      roots: [services]
      terms: [visibility]
      files:
{files}
    compatibility:
      strategy: {strategy}
      compatibilityPaths: [services/domain/migration.sql]
      proofIds: [proof.red-one]
    proofIds: [proof.red-one]
```
"""
    return text.replace("## ACDD inputs", f"{matrix}\n## ACDD inputs")


def test_persisted_contract_discovery_closes_every_pipeline_role(
    tmp_path: Path,
) -> None:
    text = _value_domain_text(tmp_path)
    semantic = FP.semantic_task_fingerprint(text)
    domains = VALUE_DOMAINS.parse_value_domains(
        text,
        workspace_root=tmp_path,
        declared_paths=frozenset(item.path for item in FP.parse_inputs(text)),
        semantic_ids=frozenset(semantic.ids),
    )
    assert [
        (domain.id, domain.change, domain.compatibility_impact) for domain in domains
    ] == [("contract.visibility", "changed", "restriction")]


def test_persisted_contract_discovery_rejects_an_omitted_candidate(
    tmp_path: Path,
) -> None:
    text = _value_domain_text(tmp_path, include_reader_disposition=False)
    semantic = FP.semantic_task_fingerprint(text)
    with pytest.raises(VALUE_DOMAINS.ValueDomainError, match="discovery closure mismatch"):
        VALUE_DOMAINS.parse_value_domains(
            text,
            workspace_root=tmp_path,
            declared_paths=frozenset(item.path for item in FP.parse_inputs(text)),
            semantic_ids=frozenset(semantic.ids),
        )


def test_persisted_contract_discovery_uses_code_roots_and_ignores_pi_runtime_artifacts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "contextunity" / "services" / "owner.py"
    source.parent.mkdir(parents=True)
    source.write_text("upsert_graph\n", encoding="utf-8")
    docs = tmp_path / "contextunity" / "docs" / "reference.md"
    docs.parent.mkdir(parents=True)
    docs.write_text("upsert_graph\n", encoding="utf-8")
    artifact = tmp_path / "contextunity" / ".pi-subagents" / "artifacts" / "reviewer.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("upsert_graph\n", encoding="utf-8")

    assert VALUE_DOMAINS._discover(
        tmp_path,
        roots=["contextunity"],
        terms=["upsert_graph"],
        label="test.discovery",
    ) == {"contextunity/services/owner.py"}


def test_non_enum_contract_restriction_cannot_pass_without_compatibility_strategy(
    tmp_path: Path,
) -> None:
    text = _value_domain_text(
        tmp_path,
        strategy="not-required",
        contract_kind="numeric-range",
        before_contract="{minimum: 0, maximum: 100}",
        after_contract="{minimum: 10, maximum: 90}",
    )
    semantic = FP.semantic_task_fingerprint(text)
    with pytest.raises(
        VALUE_DOMAINS.ValueDomainError,
        match="compatibility-breaking persisted contract change requires backfill",
    ):
        VALUE_DOMAINS.parse_value_domains(
            text,
            workspace_root=tmp_path,
            declared_paths=frozenset(item.path for item in FP.parse_inputs(text)),
            semantic_ids=frozenset(semantic.ids),
        )


def _architecture_document(
    tmp_path: Path, *, review_overrides: dict[str, str] | None = None
) -> tuple[Path, tuple[Path, ...]]:
    document, adapters = _fixture(tmp_path)
    implementation_dir = tmp_path / ".acdd"
    implementation_dir.mkdir()
    implementation = implementation_dir / "implementation-adapter.yaml"
    implementation.write_text(adapters[1].read_text(encoding="utf-8"), encoding="utf-8")
    source = tmp_path / "services" / "source.py"
    source.parent.mkdir()
    source.write_text((tmp_path / "source.py").read_text(encoding="utf-8"), encoding="utf-8")
    document.write_text(
        document.read_text(encoding="utf-8").replace("path: source.py", "path: services/source.py", 1),
        encoding="utf-8",
    )
    adapters = (adapters[0], implementation)
    core = VALIDATOR.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    policies = {policy.gate: policy for policy in VALIDATOR._gate_policies(core)}
    matrix_fp = FP.fingerprint_inputs(
        document=document,
        profile=core.profile_path,
        receipt_contract=core.receipt_contract_path,
        adapters=adapters,
        workspace_root=tmp_path,
        include_types=policies["matrix/v1"].invalidation_inputs,
    ).sha256
    architecture_fp = FP.fingerprint_architecture_code_inputs(
        document=document,
        adapters=adapters,
        workspace_root=tmp_path,
    ).sha256
    fields = {
        "independent": "true",
        "sessionUuid": "019f8f5f-003b-7374-bcbf-00ff511958b0",
        "authorSessionUuid": "019f86f9-e306-79b5-8007-dda62c0f90a1",
        "contradictions": "[]",
        "impactAxes": "{deployment: affected}",
        "inventoryComplete": "true",
        "decisionsResolved": "true",
        "callerCoverageComplete": "true",
        "persistedContractChange": "false",
        "persistedContractMappings": "[]",
        "discoveryComplete": "true",
    }
    fields.update(review_overrides or {})
    evidence = f"""```yaml
apiVersion: acdd/gate-evidence/v1
kind: basis
id: matrix.pass
gate: matrix/v1
inputFingerprint: {matrix_fp}
summary: complete
authoritySources: [task.md]
mappings: [contract.proof]
contradictions: []
---
apiVersion: acdd/gate-evidence/v1
kind: review
id: architecture.pass
gate: architecture/v1
inputFingerprint: {architecture_fp}
adapter: fixture/v1
sessionUuid: {fields["sessionUuid"]}
authorSessionUuid: {fields["authorSessionUuid"]}
reviewer: reviewer
independent: {fields["independent"]}
terminalVerdict: PASS
authoritySources: [task.md]
productionPaths: [caller -> owner]
directCallers: [caller]
alternateCallers: []
contradictions: {fields["contradictions"]}
impactAxes: {fields["impactAxes"]}
matrixMappings: [contract.proof]
proofMappings: [proof.red-one]
findings: []
inventoryComplete: {fields["inventoryComplete"]}
decisionsResolved: {fields["decisionsResolved"]}
callerCoverageComplete: {fields["callerCoverageComplete"]}
persistedContractChange: {fields["persistedContractChange"]}
persistedContractMappings: {fields["persistedContractMappings"]}
discoveryComplete: {fields["discoveryComplete"]}
verification:
  inputFingerprint: {architecture_fp}
  runtime: pi
  capabilities: [independent_review, review_execution]
  isolated: true
  readOnly: true
  authoritativeSessionUuids: [019f8f5f-003b-7374-bcbf-00ff511958b0]
  persistedContractIds: []
  usage:
    launches: []
    totals:
      input: 0
      output: 0
      cacheRead: 0
      cacheWrite: 0
      cost: 0
      totalTokens: 0
  partitions:
    - id: contract
      status: pass
      inputFingerprint: {architecture_fp}
      evidence: [services/source.py:1]
      findings: []
      discovery: &repository_discovery
        repositoryRoot: .
        methods:
          exactText:
            capability: source_map
            tools: [grep]
            queries: [changed identifiers and literals]
            complete: true
          structural:
            capability: structural_search
            tools: [ast_grep_search]
            queries: [writers readers and alternate implementations]
            complete: true
          dependency:
            capability: impact
            tools: [code_map_query]
            queries: [reverse dependencies and cross-service paths]
            complete: true
      persistedContractMappings: []
      isolated: true
      readOnly: true
    - id: authority
      status: pass
      inputFingerprint: {architecture_fp}
      evidence: [services/source.py:2]
      findings: []
      discovery: *repository_discovery
      persistedContractMappings: []
      isolated: true
      readOnly: true
    - id: callers
      status: pass
      inputFingerprint: {architecture_fp}
      evidence: [services/source.py:3]
      findings: []
      discovery: *repository_discovery
      persistedContractMappings: []
      isolated: true
      readOnly: true
    - id: persistence
      status: pass
      inputFingerprint: {architecture_fp}
      evidence: [services/source.py:4]
      findings: []
      discovery: *repository_discovery
      persistedContractMappings: []
      isolated: true
      readOnly: true
  coordinator:
    sessionUuid: 019f8f5f-003b-7374-bcbf-00ff511958b0
    verdict: PASS
    findingsReconciled: true
    persistedContractsReconciled: true
    resolvedFindings: []
    reconciledRecommendations: []
```"""
    text = document.read_text(encoding="utf-8").replace("```yaml\n[]\n```", evidence)
    text = text.replace(
        "| `matrix/v1` | `pending` | pending | `pending` | `pending` |",
        f"| `matrix/v1` | `pass` | evidence=matrix.pass | `{matrix_fp}` | `2026-07-23T00:00:00Z` |",
    ).replace(
        "| `architecture/v1` | `pending` | pending | `pending` | `pending` |",
        f"| `architecture/v1` | `pass` | evidence=architecture.pass | `{architecture_fp}` | `2026-07-23T00:00:00Z` |",
    )
    document.write_text(text, encoding="utf-8")
    return document, adapters


def test_complete_architecture_review_can_pass(tmp_path: Path) -> None:
    document, adapters = _architecture_document(tmp_path)
    core = VALIDATOR.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    DOC.validate_document(
        document=document,
        profile=core.profile_path,
        receipt_contract=core.receipt_contract_path,
        adapters=adapters,
        workspace_root=tmp_path,
        policies=VALIDATOR._gate_policies(core),
        plan=False,
        impact_axes=frozenset({"deployment"}),
        architecture_verification_schema=core.architecture_verification_schema,
        architecture_verification_contract=VALIDATOR.load_architecture_verification_yaml(
            ROOT / "examples" / "task" / "architecture-verification.yaml"
        ),
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"inventoryComplete": "false"}, "inventoryComplete"),
        ({"decisionsResolved": "false"}, "decisionsResolved"),
        ({"callerCoverageComplete": "false"}, "callerCoverageComplete"),
        ({"contradictions": "[open]"}, "unresolved contradictions"),
        ({"impactAxes": "{operations: affected}"}, "impact-axis coverage"),
        (
            {
                "authorSessionUuid": "019f8f5f-003b-7374-bcbf-00ff511958b0"
            },
            "independent-session provenance",
        ),
    ],
)
def test_incomplete_architecture_review_cannot_pass(
    tmp_path: Path, overrides: dict[str, str], message: str
) -> None:
    document, adapters = _architecture_document(
        tmp_path, review_overrides=overrides
    )
    core = VALIDATOR.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    with pytest.raises(DOC.DocumentError, match=message):
        DOC.validate_document(
            document=document,
            profile=core.profile_path,
            receipt_contract=core.receipt_contract_path,
            adapters=adapters,
            workspace_root=tmp_path,
            policies=VALIDATOR._gate_policies(core),
            plan=False,
            impact_axes=frozenset({"deployment"}),
            architecture_verification_schema=core.architecture_verification_schema,
            architecture_verification_contract=VALIDATOR.load_architecture_verification_yaml(
                ROOT / "examples" / "task" / "architecture-verification.yaml"
            ),
        )


def test_profile_migration_cannot_drop_ids(tmp_path: Path) -> None:
    document, _ = _fixture(tmp_path)
    current = FP.semantic_task_fingerprint(document.read_text(encoding="utf-8"))
    record = DOC.SemanticRecord(
        sha256="sha256:" + "1" * 64,
        ids=("decision.one", "proof.removed"),
        red_proof_sha256=current.red_proof_sha256,
        red_evidence_ids=(),
    )
    change = f"""## ACDD contract changes

```yaml
apiVersion: acdd/contract-change/v1
kind: profile-migration
beforeFingerprint: {current.sha256}
afterFingerprint: {current.sha256}
beforeIds: [decision.one, proof.removed]
afterIds: [decision.one]
```"""
    text = document.read_text(encoding="utf-8") + "\n" + change
    receipts = DOC.parse_receipts(text, plan=False)
    with pytest.raises(DOC.DocumentError, match="preserve semantic fingerprint and IDs"):
        DOC._validate_contract_changes(
            text,
            current=current,
            record=record,
            receipts=receipts,
            gate_order=tuple(receipt.gate for receipt in receipts),
        )


def test_profile_only_migration_preserves_semantics(tmp_path: Path) -> None:
    document, _ = _fixture(tmp_path)
    current = FP.semantic_task_fingerprint(document.read_text(encoding="utf-8"))
    record = DOC.SemanticRecord(
        sha256=current.sha256,
        ids=current.ids,
        red_proof_sha256=current.red_proof_sha256,
        red_evidence_ids=(),
    )
    ids = ", ".join(current.ids)
    change = f"""## ACDD contract changes

```yaml
apiVersion: acdd/contract-change/v1
kind: profile-migration
beforeFingerprint: {current.sha256}
afterFingerprint: {current.sha256}
beforeIds: [{ids}]
afterIds: [{ids}]
```"""
    text = document.read_text(encoding="utf-8") + "\n" + change
    receipts = DOC.parse_receipts(text, plan=False)
    DOC._validate_contract_changes(
        text,
        current=current,
        record=record,
        receipts=receipts,
        gate_order=tuple(receipt.gate for receipt in receipts),
    )


def test_authorized_semantic_change_accepts_explicit_removal_and_pending_reset(
    tmp_path: Path,
) -> None:
    document, _ = _fixture(tmp_path)
    current = FP.semantic_task_fingerprint(document.read_text(encoding="utf-8"))
    old = DOC.SemanticRecord(
        sha256="sha256:" + "1" * 64,
        ids=tuple(sorted((*current.ids, "proof.removed"))),
        red_proof_sha256=current.red_proof_sha256,
        red_evidence_ids=(),
    )
    change = f"""## ACDD contract changes

```yaml
apiVersion: acdd/contract-change/v1
kind: semantic-change
rationale: remove obsolete proof
authorization: bound user decision
beforeFingerprint: {old.sha256}
afterFingerprint: {current.sha256}
removedIds: [proof.removed]
```"""
    text = document.read_text(encoding="utf-8") + "\n" + change
    receipts = DOC.parse_receipts(text, plan=False)
    DOC._validate_contract_changes(
        text,
        current=current,
        record=old,
        receipts=receipts,
        gate_order=tuple(receipt.gate for receipt in receipts),
    )


def test_legacy_manifest_references_are_rejected(tmp_path: Path) -> None:
    document, _ = _fixture(tmp_path)
    text = document.read_text(encoding="utf-8").replace(
        "| `pending` | pending", "| `blocked` | manifest=.acdd/input-set.json", 1
    )
    with pytest.raises(DOC.DocumentError, match="legacy manifest"):
        DOC.parse_receipts(text, plan=False)

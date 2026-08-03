from __future__ import annotations

import copy
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "validate_acdd", SCRIPTS / "validate_acdd.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

import acdd_document as DOCUMENT
import architecture_verification as ARCH
import workflow_learning as LEARNING


def _discovery_receipt() -> dict[str, object]:
    return {
        "repositoryRoot": ".",
        "methods": {
            "exactText": {
                "capability": "source_map",
                "tools": ["grep"],
                "queries": ["changed identifiers and literals across repository"],
                "complete": True,
            },
            "structural": {
                "capability": "structural_search",
                "tools": ["ast_grep_search"],
                "queries": ["writers, readers, validators, and alternate implementations"],
                "complete": True,
            },
            "dependency": {
                "capability": "impact",
                "tools": ["code_map_query"],
                "queries": ["reverse dependencies and cross-service paths"],
                "complete": True,
            },
        },
    }

def _verification_result(*, runtime: str = "pi") -> dict[str, object]:
    fingerprint = "sha256:" + "1" * 64
    session = "83b57c2d-75ed-4dee-9f50-e20818ab6f53"
    return {
        "inputFingerprint": fingerprint,
        "runtime": runtime,
        "capabilities": ["independent_review", "review_execution"],
        "isolated": True,
        "readOnly": True,
        "authoritativeSessionUuids": [session],
        "persistedContractIds": [],
        "usage": {
            "launches": [],
            "totals": {
                "input": 0, "output": 0, "cacheRead": 0,
                "cacheWrite": 0, "cost": 0, "totalTokens": 0,
            },
        },
        "partitions": [
            {
                "id": partition,
                "status": "pass",
                "inputFingerprint": fingerprint,
                "evidence": [f"services/{partition}.py:1"],
                "findings": [],
                "discovery": _discovery_receipt(),
                "persistedContractMappings": [],
                "isolated": True,
                "readOnly": True,
            }
            for partition in ("contract", "authority", "callers", "persistence")
        ],
        "coordinator": {
            "sessionUuid": session,
            "verdict": "PASS",
            "findingsReconciled": True,
            "persistedContractsReconciled": True,
            "resolvedFindings": [],
            "reconciledRecommendations": [],
        },
    }


def _architectural_recommendation() -> dict[str, object]:
    return {
        "id": "owner-boundary-1",
        "sourceFindings": ["callers:1"],
        "invariant": "The canonical contract is uniform for every production caller.",
        "rootCause": "The contract is enforced in one caller instead of its owner.",
        "canonicalOwner": "packages/core public contract and owning service boundary",
        "requiredChange": "Enforce the invariant at the owner and propagate the canonical type.",
        "propagation": ["direct callers", "alternate callers", "transport", "storage backends"],
        "prohibitedShortcuts": ["caller-local branch", "compatibility cast", "fallback"],
        "acceptanceProof": ["owner unit proof", "caller parity proof", "backend parity proof"],
        "evidence": ["services/callers.py:1"],
        "userDecisionRequired": False,
        "decisionOptions": [],
    }


def _candidate_finding() -> dict[str, object]:
    return {
        "id": "callers-contract-gap",
        "defectKind": "incomplete-propagation",
        "candidateDefect": "The task omits one production caller.",
        "taskEvidence": ["task.md:10"],
        "codeEvidence": ["services/callers.py:1"],
        "requiredTaskChange": "Add the caller and its proof to the task contract.",
    }


def test_both_profiles_load_with_shared_inline_receipt_model() -> None:
    task = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    plan = MODULE.load_core(ROOT / "profiles" / "plan" / "v1.yaml")
    assert task.profile["id"] == "acdd/task/v1"
    assert plan.profile["id"] == "acdd/plan/v1"
    assert task.receipt_contract["invalidationInputs"] == plan.receipt_contract[
        "invalidationInputs"
    ]
    assert task.architecture_verification_schema is not None
    assert plan.architecture_verification_schema is None
    assert task.workflow_learning_contract is not None
    assert task.workflow_learning_contract == plan.workflow_learning_contract
    assert task.workflow_learning_contract["verdictEffect"] == "none"
    assert task.workflow_learning_contract["receiptEffect"] == "none"


def test_workflow_learning_example_matches_canonical_contract() -> None:
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    assert core.workflow_learning_contract is not None
    example = MODULE._mapping(ROOT / "examples" / "task" / "workflow-learning.yaml")
    assert (
        LEARNING.validate_record(example, core.workflow_learning_contract)["status"]
        == "analyzed"
    )


def test_workflow_learning_candidate_requires_a_confirmed_finding() -> None:
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    example = MODULE._mapping(ROOT / "examples" / "task" / "workflow-learning.yaml")
    example["candidates"][0]["sourceFindings"] = []
    with pytest.raises(LEARNING.WorkflowLearningError, match="sourceFindings"):
        LEARNING.validate_record(example, core.workflow_learning_contract)


def test_example_adapters_cover_routed_capabilities() -> None:
    task = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    plan = MODULE.load_core(ROOT / "profiles" / "plan" / "v1.yaml")
    task_adapter = MODULE.load_adapter(
        ROOT / "examples" / "planner" / ".acdd-legacy" / "task-adapter.yaml",
        "task",
        task,
        allowed_root=ROOT,
    )
    discovery = task_adapter["gateProcedures"]["architecture/v1"]["discoveryMethods"]
    assert discovery["exactText"]["capability"] == "source_map"
    assert discovery["structural"]["capability"] == "structural_search"
    assert discovery["dependency"]["capability"] == "impact"
    assert discovery["dependency"]["tools"] == ["code_map_query"]
    architecture = task_adapter["gateProcedures"]["architecture/v1"]
    assert architecture["runtime"] == "pi"
    assert architecture["launchers"]["inspector"]["target"] == "pi"
    assert architecture["launchers"]["coordinator"]["target"] == "pi"
    assert architecture["runtime"] not in architecture["toolEnvelope"]["admit"]
    implementation_adapter = MODULE.load_adapter(
        ROOT / "examples" / "codebase" / ".acdd-legacy" / "implementation-adapter.yaml",
        "implementation",
        task,
        allowed_root=ROOT,
    )
    review = implementation_adapter["gateProcedures"]["review/v1"]
    assert review["launcher"]["target"] == "pi_review_agents"
    assert review["launcher"]["target"] in review["toolEnvelope"]["admit"]
    for relative in (
        "examples/simple-plan/.acdd-legacy/plan-adapter.yaml",
        "examples/planner/.acdd-legacy/plan-adapter.yaml",
        "examples/linear/.acdd-legacy/plan-adapter.yaml",
        "examples/jira/.acdd-legacy/plan-adapter.yaml",
    ):
        MODULE.load_adapter(
            ROOT / relative,
            "plan",
            plan,
            allowed_root=ROOT,
        )


def test_declared_paths_do_not_treat_model_ids_or_arguments_as_files(
    tmp_path: Path,
) -> None:
    owner = tmp_path / "implementation-adapter.yaml"
    owner.write_text("adapter", encoding="utf-8")
    reference = tmp_path / "review.md"
    reference.write_text("review", encoding="utf-8")
    procedure = {
        "review/v1": {
            "reference": "review.md",
            "reviewers": [
                {"model": "antigravity/gemini-3.6-flash-high"},
            ],
            "piInvocation": {
                "arguments": ["--extension", "/opt/pi/extensions/reviewer.ts"],
            },
        },
    }

    MODULE._validate_declared_paths(
        procedure,
        owner,
        "adapter.gateProcedures",
        allowed_root=tmp_path,
    )

    procedure["review/v1"]["reference"] = "missing.md"
    with pytest.raises(MODULE.ContractError, match="missing 'missing.md'"):
        MODULE._validate_declared_paths(
            procedure,
            owner,
            "adapter.gateProcedures",
            allowed_root=tmp_path,
        )

def test_task_architecture_launchers_bind_models() -> None:
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    adapter_path = ROOT / "examples" / "planner" / ".acdd-legacy" / "task-adapter.yaml"
    adapter = MODULE.load_adapter(adapter_path, "task", core, allowed_root=ROOT)
    procedures = copy.deepcopy(adapter["gateProcedures"])
    architecture = procedures["architecture/v1"]
    MODULE._validate_executor_gate_procedures(
        procedures,
        core,
        "task",
        adapter_path,
        ROOT,
        "adapter.gateProcedures",
    )

    arguments = architecture["launchers"]["inspector"]["arguments"]
    del arguments[arguments.index("--model")]
    with pytest.raises(MODULE.ContractError, match="inspector launcher must bind --model exactly once"):
        MODULE._validate_executor_gate_procedures(
            procedures,
            core,
            "task",
            adapter_path,
            ROOT,
            "adapter.gateProcedures",
        )


def test_task_architecture_requires_split_launchers() -> None:
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    adapter_path = ROOT / "examples" / "planner" / ".acdd-legacy" / "task-adapter.yaml"
    adapter = MODULE.load_adapter(adapter_path, "task", core, allowed_root=ROOT)
    procedures = copy.deepcopy(adapter["gateProcedures"])
    architecture = procedures["architecture/v1"]
    coordinator_arguments = architecture["launchers"]["coordinator"]["arguments"]
    MODULE._validate_executor_gate_procedures(
        procedures, core, "task", adapter_path, ROOT, "adapter.gateProcedures"
    )
    coordinator_arguments[-1:] = ["--tools", "mcp"]
    with pytest.raises(MODULE.ContractError, match="coordinator launcher must disable all tools"):
        MODULE._validate_executor_gate_procedures(
            procedures, core, "task", adapter_path, ROOT, "adapter.gateProcedures"
        )
    coordinator_arguments[-2:] = ["--no-tools"]
    architecture["launcher"] = architecture.pop("launchers")["inspector"]
    with pytest.raises(MODULE.ContractError, match="requires inspector and coordinator launchers"):
        MODULE._validate_executor_gate_procedures(
            procedures, core, "task", adapter_path, ROOT, "adapter.gateProcedures"
        )


def test_architecture_accepts_host_neutral_split_command_launchers() -> None:
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    adapter_path = ROOT / "examples" / "planner" / ".acdd-legacy" / "task-adapter.yaml"
    adapter = MODULE.load_adapter(adapter_path, "task", core, allowed_root=ROOT)
    procedures = copy.deepcopy(adapter["gateProcedures"])
    architecture = procedures["architecture/v1"]
    architecture["runtime"] = "host-collaboration"
    architecture["launchers"] = {
        role: {
            "kind": "command",
            "target": "python3",
            "arguments": ["bridge.py", "--role", role, "--session", "{sessionUuid}"],
            "promptTransport": "final-argument",
        }
        for role in ("inspector", "coordinator")
    }
    MODULE._validate_executor_gate_procedures(
        procedures, core, "task", adapter_path, ROOT, "adapter.gateProcedures"
    )

def test_reviewer_adapter_examples_bind_owner_roles_and_code_map_impact() -> None:
    task = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    plan = MODULE.load_core(ROOT / "profiles" / "plan" / "v1.yaml")
    reviewer_root = ROOT / "examples" / "reviewers" / ".acdd-legacy"

    task_adapter = MODULE.load_adapter(
        reviewer_root / "task-adapter.yaml", "task", task, allowed_root=ROOT
    )
    dependency = task_adapter["gateProcedures"]["architecture/v1"][
        "discoveryMethods"
    ]["dependency"]
    assert dependency == {"capability": "impact", "tools": ["code_map_query"]}

    implementation_adapter = MODULE.load_adapter(
        reviewer_root / "implementation-adapter.yaml",
        "implementation",
        task,
        allowed_root=ROOT,
    )
    implementation_review = implementation_adapter["gateProcedures"]["review/v1"]
    assert implementation_review["launcher"]["target"] == "pi_review_agents"
    assert "code_map_query" in implementation_review["toolEnvelope"]["admit"]
    assert "ctx_impact" not in implementation_review["toolEnvelope"]["admit"]

    plan_adapter = MODULE.load_adapter(
        reviewer_root / "plan-adapter.yaml", "plan", plan, allowed_root=ROOT
    )
    plan_review = plan_adapter["gateProcedures"]["review/v1"]
    assert plan_review["launcher"]["target"] == "pi_review_agents"
    assert "code_map_query" in plan_review["toolEnvelope"]["admit"]


def test_default_write_policy_blocks_agent_instructions() -> None:
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    adapter = MODULE.load_adapter(
        ROOT / "examples" / "codebase" / ".acdd-legacy" / "implementation-adapter.yaml",
        "implementation",
        core,
        allowed_root=ROOT,
    )

    assert MODULE.validate_adapter_write_path(core, adapter, "src/service.py") == (
        "src/service.py"
    )
    for protected in (
        ".agents/skills/example/SKILL.md",
        "service/.agents/workflows/release.md",
        "AGENTS.md",
        "service/AGENTS.md",
    ):
        with pytest.raises(MODULE.ContractError, match="is protected"):
            MODULE.validate_adapter_write_path(core, adapter, protected)


def test_protected_write_requires_scoped_policy_and_explicit_user_request() -> None:
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    adapter = MODULE.load_adapter(
        ROOT / "examples" / "codebase" / ".acdd-legacy" / "implementation-adapter.yaml",
        "implementation",
        core,
        allowed_root=ROOT,
    )
    adapter["writePolicy"] = {
        "protectedAllow": [".agents/skills/example/**"],
        "authorization": "explicit-user-request",
    }
    skill_path = ".agents/skills/example/SKILL.md"

    with pytest.raises(MODULE.ContractError, match="explicit user request"):
        MODULE.validate_adapter_write_path(core, adapter, skill_path)
    assert MODULE.validate_adapter_write_path(
        core, adapter, skill_path, explicit_user_request=True
    ) == skill_path
    with pytest.raises(MODULE.ContractError, match="is protected"):
        MODULE.validate_adapter_write_path(
            core,
            adapter,
            ".agents/skills/other/SKILL.md",
            explicit_user_request=True,
        )


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        (
            {"allow": ["src/**"], "deny": ["src/**"]},
            "allow and deny patterns overlap",
        ),
        (
            {"deny": ["../.agents/**"]},
            "normalized workspace-relative paths",
        ),
        (
            {"protectedAllow": [".agents/skills/example/**"]},
            "authorization must be 'explicit-user-request'",
        ),
        (
            {
                "protectedAllow": [".agents/**"],
                "authorization": "explicit-user-request",
            },
            "must be narrower than protected defaults",
        ),
    ],
)
def test_invalid_adapter_write_policy_fails_closed(
    policy: dict[str, object], message: str
) -> None:
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    with pytest.raises(MODULE.ContractError, match=message):
        MODULE._adapter_write_policy(policy, core, "adapter.writePolicy")


def test_adapter_deny_precedes_explicit_protected_allow() -> None:
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    adapter = {
        "writePolicy": {
            "deny": [".agents/skills/example/SKILL.md"],
            "protectedAllow": [".agents/skills/example/**"],
            "authorization": "explicit-user-request",
        }
    }
    with pytest.raises(MODULE.ContractError, match="denied by adapter.writePolicy"):
        MODULE.validate_adapter_write_path(
            core,
            adapter,
            ".agents/skills/example/SKILL.md",
            explicit_user_request=True,
        )


def test_acdd_skills_require_adapter_relative_path_resolution() -> None:
    required = (
        "resolve its relative path from the adapter file's directory",
        "verify that the resolved target exists",
        "Never reinterpret it from the session working directory",
        "search/glob miss",
        "treat `runtime` as provenance only",
        "Never search for or invoke it as a tool",
        "`launcher.target`",
    )
    for relative in ("skills/acdd-task/SKILL.md", "skills/acdd-plan/SKILL.md"):
        text = " ".join((ROOT / relative).read_text(encoding="utf-8").split())
        assert all(fragment in text for fragment in required)


def test_capability_incomplete_adapter_fails_closed(tmp_path: Path) -> None:
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    adapter = tmp_path / "task.yaml"
    adapter.write_text(
        """apiVersion: acdd/adapter/v1
kind: adapter
id: task/v1
role: task
provides: [task_read]
procedure: [Read task.]
authority: {task: fixture}
constraints: [Use current evidence.]
""",
        encoding="utf-8",
    )
    with pytest.raises(MODULE.ContractError, match="must provide exactly"):
        MODULE.load_adapter(adapter, "task", core)


def test_duplicate_adapter_role_is_rejected() -> None:
    with pytest.raises(MODULE.ContractError, match="duplicate adapter role"):
        MODULE._adapter_args(["task=a.yaml", "task=b.yaml"])


def test_task_routes_have_gate_specific_executor_owners() -> None:
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    assert core.route_executors["architecture/v1"] == "task"
    assert core.route_executors["review/v1"] == "implementation"


def test_parallel_verification_is_read_only_and_requires_every_partition() -> None:
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    assert core.architecture_verification_schema is not None
    contract = ARCH.load_yaml(ROOT / "examples" / "task" / "architecture-verification.yaml")
    ARCH.validate_contract(contract, core.architecture_verification_schema)
    result = _verification_result()
    ARCH.validate_result(contract, core.architecture_verification_schema, result)

    missing = _verification_result()
    missing["partitions"] = list(missing["partitions"])[:-1]
    with pytest.raises(ARCH.ArchitectureVerificationError, match="cover every partition"):
        ARCH.validate_result(contract, core.architecture_verification_schema, missing)


    incomplete_discovery = _verification_result()
    del incomplete_discovery["partitions"][0]["discovery"]["methods"]["dependency"]
    with pytest.raises(
        ARCH.ArchitectureVerificationError,
        match="must contain exactText, structural, and dependency",
    ):
        ARCH.validate_result(
            contract, core.architecture_verification_schema, incomplete_discovery
        )

    inspector_receipt = _verification_result()
    inspector_receipt["partitions"][0]["receipt"] = "forbidden"
    with pytest.raises(ARCH.ArchitectureVerificationError, match="cannot contain"):
        ARCH.validate_result(
            contract, core.architecture_verification_schema, inspector_receipt
        )

    legacy_contract = copy.deepcopy(contract)
    legacy_contract["coordinatorPolicy"].pop("allowResolvedFindings")
    legacy_contract.pop("findingContract")
    ARCH.validate_contract(legacy_contract, core.architecture_verification_schema)


def test_architecture_contract_requires_every_canonical_guidance_axis() -> None:
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    assert core.architecture_verification_schema is not None
    contract = ARCH.load_yaml(ROOT / "examples" / "task" / "architecture-verification.yaml")
    incomplete = copy.deepcopy(contract)
    incomplete["inspectors"][2]["covers"].remove("production-path")

    with pytest.raises(
        ARCH.ArchitectureVerificationError,
        match="misses required guidance axes: .*production-path",
    ):
        ARCH.validate_contract(incomplete, core.architecture_verification_schema)


def test_proof_obligation_mapping_shape_and_terminal_pending_policy() -> None:
    example = (ROOT / "examples" / "task" / "TASK.md").read_text(encoding="utf-8")
    assert DOCUMENT.validate_proof_obligation_mapping(example, terminal=False) == (
        "proof.example-red",
        "proof.example-scope",
        "proof.example-parity",
    )

    pending = """## Proof obligation mapping

| Proof ID | Boundary | Required scenarios | Execution evidence |
|---|---|---|---|
| `proof.pending` | storage | concurrent winner and loser | pending |
"""
    assert DOCUMENT.validate_proof_obligation_mapping(pending, terminal=False) == (
        "proof.pending",
    )
    with pytest.raises(DOCUMENT.DocumentError, match="remains pending"):
        DOCUMENT.validate_proof_obligation_mapping(pending, terminal=True)


def test_proof_obligation_mapping_rejects_incomplete_and_duplicate_rows() -> None:
    incomplete = """## Proof obligation mapping

| Proof ID | Boundary | Required scenarios | Execution evidence |
|---|---|---|---|
| `proof.example` | storage | - | pending |
"""
    with pytest.raises(DOCUMENT.DocumentError, match="row 1 is incomplete"):
        DOCUMENT.validate_proof_obligation_mapping(incomplete, terminal=False)

    duplicate = incomplete.replace("| storage | - |", "| storage | scenario |") + (
        "| `proof.example` | decoder | scenario | pending |\n"
    )
    with pytest.raises(DOCUMENT.DocumentError, match="duplicate proof IDs"):
        DOCUMENT.validate_proof_obligation_mapping(duplicate, terminal=False)

    missing_named = duplicate.replace(
        "| `proof.example` | decoder | scenario | pending |\n",
        "\n## Named proof IDs\n\n- `proof.other`\n",
    )
    with pytest.raises(DOCUMENT.DocumentError, match="misses named proof IDs"):
        DOCUMENT.validate_proof_obligation_mapping(missing_named, terminal=False)


def test_fail_requires_complete_coordinator_recommendation_and_exact_finding_coverage() -> None:
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    assert core.architecture_verification_schema is not None
    contract = ARCH.load_yaml(ROOT / "examples" / "task" / "architecture-verification.yaml")
    result = _verification_result()
    result["partitions"][2]["status"] = "fail"
    result["partitions"][2]["findings"] = [_candidate_finding()]
    result["coordinator"]["verdict"] = "FAIL"
    result["coordinator"]["reconciledRecommendations"] = [_architectural_recommendation()]
    ARCH.validate_result(contract, core.architecture_verification_schema, result)

    missing_owner = copy.deepcopy(result)
    del missing_owner["coordinator"]["reconciledRecommendations"][0]["canonicalOwner"]
    with pytest.raises(ARCH.ArchitectureVerificationError, match="decision-aware"):
        ARCH.validate_result(contract, core.architecture_verification_schema, missing_owner)

    missing_finding = copy.deepcopy(result)
    missing_finding["coordinator"]["reconciledRecommendations"][0]["sourceFindings"] = ["authority:1"]
    with pytest.raises(ARCH.ArchitectureVerificationError, match="every inspector finding"):
        ARCH.validate_result(contract, core.architecture_verification_schema, missing_finding)

    raw_only = copy.deepcopy(result)
    raw_only["coordinator"]["reconciledRecommendations"] = []
    with pytest.raises(ARCH.ArchitectureVerificationError, match="architecturally complete"):
        ARCH.validate_result(contract, core.architecture_verification_schema, raw_only)

    ambiguous = copy.deepcopy(result)
    recommendation = ambiguous["coordinator"]["reconciledRecommendations"][0]
    recommendation["userDecisionRequired"] = True
    recommendation["decisionOptions"] = [
        "update-task: choose the canonical boundary in the current task",
        "create-linked-plan: extract the cross-phase redesign and link it to this task",
    ]
    ARCH.validate_result(contract, core.architecture_verification_schema, ambiguous)

    incomplete_options = copy.deepcopy(ambiguous)
    incomplete_options["coordinator"]["reconciledRecommendations"][0][
        "decisionOptions"
    ] = ["update-task: choose one interpretation"]
    with pytest.raises(
        ARCH.ArchitectureVerificationError, match="requires update-task"
    ):
        ARCH.validate_result(
            contract, core.architecture_verification_schema, incomplete_options
        )


def test_capability_validation_accepts_equivalent_83b_runtime() -> None:
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    assert core.architecture_verification_schema is not None
    contract = ARCH.load_yaml(ROOT / "examples" / "task" / "architecture-verification.yaml")
    result = _verification_result(runtime="pi-review-agents")
    assert result["authoritativeSessionUuids"] == [
        "83b57c2d-75ed-4dee-9f50-e20818ab6f53"
    ]
    ARCH.validate_result(contract, core.architecture_verification_schema, result)


def test_architecture_v1_accepts_historical_result_without_usage_or_resolutions() -> None:
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    assert core.architecture_verification_schema is not None
    contract = ARCH.load_yaml(ROOT / "examples" / "task" / "architecture-verification.yaml")
    result = _verification_result()
    del result["usage"]
    del result["coordinator"]["resolvedFindings"]
    ARCH.validate_result(contract, core.architecture_verification_schema, result)


def test_architecture_usage_totals_must_match_all_launcher_attempts() -> None:
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    assert core.architecture_verification_schema is not None
    contract = ARCH.load_yaml(ROOT / "examples" / "task" / "architecture-verification.yaml")
    result = _verification_result()
    result["usage"]["launches"] = [{
        "role": "inspector",
        "partition": "contract",
        "attempt": 1,
        "sessionUuid": "83b57c2d-75ed-4dee-9f50-e20818ab6f53",
        "available": True,
        "input": 10,
        "output": 2,
        "cacheRead": 3,
        "cacheWrite": 0,
        "cost": 0.1,
        "totalTokens": 15,
    }]
    with pytest.raises(ARCH.ArchitectureVerificationError, match="totals"):
        ARCH.validate_result(contract, core.architecture_verification_schema, result)


def test_fail_retry_requires_a_changed_fingerprint_and_plan_is_explicit() -> None:
    failed = _verification_result()
    failed["partitions"][0]["status"] = "fail"
    failed["partitions"][0]["findings"] = [_candidate_finding()]
    failed["coordinator"]["verdict"] = "FAIL"
    unchanged = failed["inputFingerprint"]
    with pytest.raises(ARCH.ArchitectureVerificationError, match="unchanged FAIL"):
        ARCH.validate_retry_fingerprint(failed, unchanged)
    changed = "sha256:" + "2" * 64
    assert ARCH.validate_retry_fingerprint(failed, changed) == changed
    documentation = " ".join(
        (ROOT / "README.md").read_text(encoding="utf-8").split()
    )
    assert "rerun only after a real change" in documentation
    assert "current fingerprint" in documentation


@pytest.mark.parametrize(
    "argument", ["--binding", "--review-adapter", "--manifest", "--spec", "--components"]
)
def test_removed_cli_options_are_rejected(argument: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_acdd.py"),
            "--workspace-root",
            str(ROOT),
            "--document",
            str(ROOT / "examples" / "simple-plan" / "PLAN.md"),
            argument,
            "removed.json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert f"unrecognized arguments: {argument}" in result.stderr


def test_self_contained_plan_example_validates_without_provenance_files() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_acdd.py"),
            "--profile",
            str(ROOT / "profiles" / "plan" / "v1.yaml"),
            "--workspace-root",
            str(ROOT),
            "--document",
            str(ROOT / "examples" / "simple-plan" / "PLAN.md"),
            "--adapter",
            f"plan={ROOT / 'examples' / 'simple-plan' / '.acdd-legacy' / 'plan-adapter.yaml'}",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not list(ROOT.rglob("input-set.json"))
    assert not list(ROOT.rglob("input-spec.json"))
    assert not list(ROOT.rglob("components.json"))


def test_task_v1_light_profile_loads() -> None:
    light_profile = ROOT / "profiles" / "task" / "v1-light.yaml"
    assert light_profile.exists()
    core = MODULE.load_core(light_profile)
    assert core.profile["id"] == "acdd/task/v1-light"
    assert core.gate_ids == (
        "architecture-light/v1",
        "runtime/v1",
        "release/v1",
        "review/v1",
        "handoff/v1",
    )
    assert "architecture/v1" not in core.gate_ids
    assert "matrix/v1" not in core.gate_ids
    assert "red/v1" not in core.gate_ids
    assert core.architecture_verification_schema is None
    assert core.workflow_learning_contract["id"] == "acdd/workflow-learning/v1"


def test_v1_light_example_validates_with_light_task_adapter() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_acdd.py"),
            "--profile",
            str(ROOT / "profiles" / "task" / "v1-light.yaml"),
            "--workspace-root",
            str(ROOT),
            "--document",
            str(ROOT / "examples" / "task-light" / "TASK.md"),
            "--adapter",
            f"task={ROOT / 'examples' / 'planner' / '.acdd-legacy' / 'task-adapter-light.yaml'}",
            "--adapter",
            f"implementation={ROOT / 'examples' / 'codebase' / '.acdd-legacy' / 'implementation-adapter-light.yaml'}",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_red_evidence_structural_error_rejected(tmp_path: Path) -> None:
    from acdd_document import DocumentError, parse_evidence

    inline = _load("test_inline_evidence")
    document, _ = inline._fixture(tmp_path)
    semantic = inline.FP.semantic_task_fingerprint(document.read_text(encoding="utf-8"))
    digest = "sha256:" + "0" * 64
    lock = "sha256:" + __import__("hashlib").sha256((tmp_path / "test.py").read_bytes()).hexdigest()

    def _red_output(output: str) -> str:
        evidence = f'''```yaml
apiVersion: acdd/gate-evidence/v1
kind: command
id: red.proof
gate: red/v1
inputFingerprint: {digest}
exactCommand: pytest test.py
recordedAt: "2026-07-23T00:00:00Z"
exitCode: 1
output: "{output}"
redacted: true
result: expected_failure
expectedException: PermissionDeniedError
proofDefinitionFingerprint: {semantic.red_proof_sha256}
componentLocks:
  - path: test.py
    sha256: {lock}
```'''
        return document.read_text(encoding="utf-8").replace("```yaml\n[]\n```", evidence)

    with pytest.raises(DocumentError, match="structural error"):
        parse_evidence(
            _red_output("SyntaxError: invalid syntax"),
            workspace_root=tmp_path,
            semantic=semantic,
        )
    with pytest.raises(DocumentError, match="does not contain expectedException"):
        parse_evidence(
            _red_output("AssertionError: behavior gap"),
            workspace_root=tmp_path,
            semantic=semantic,
        )
    parsed = parse_evidence(
        _red_output("PermissionDeniedError: missing capability"),
        workspace_root=tmp_path,
        semantic=semantic,
    )
    assert parsed["red.proof"].data["expectedException"] == "PermissionDeniedError"


def _load(name: str) -> object:
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_auto_fix_receipt_fingerprints_updates_stale_rows(tmp_path: Path) -> None:
    inline = _load("test_inline_evidence")
    document, adapters = inline._fixture(tmp_path)
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    policies = {policy.gate: policy for policy in MODULE._gate_policies(core)}
    matrix_fp = inline.FP.fingerprint_inputs(
        document=document,
        profile=core.profile_path,
        receipt_contract=core.receipt_contract_path,
        adapters=adapters,
        workspace_root=tmp_path,
        include_types=policies["matrix/v1"].invalidation_inputs,
    ).sha256
    text = document.read_text(encoding="utf-8")
    text = text.replace(
        "| `matrix/v1` | `pending` | pending | `pending` | `pending` |",
        f"| `matrix/v1` | `pass` | evidence=matrix.pass | `sha256:{'1' * 64}` | `2026-07-23T00:00:00Z` |",
    )
    evidence = f'''```yaml
apiVersion: acdd/gate-evidence/v1
kind: basis
id: matrix.pass
gate: matrix/v1
inputFingerprint: {matrix_fp}
summary: complete
authoritySources: [task.md]
mappings: [contract.proof]
contradictions: []
```'''
    text = text.replace("```yaml\n[]\n```", evidence)
    document.write_text(text, encoding="utf-8")

    repaired = MODULE.auto_fix_receipt_fingerprints(
        document_path=document,
        core=core,
        adapters=adapters,
        workspace_root=tmp_path,
    )
    assert repaired is True
    updated = document.read_text(encoding="utf-8")
    assert matrix_fp in updated
    assert f"`sha256:{'1' * 64}`" not in updated

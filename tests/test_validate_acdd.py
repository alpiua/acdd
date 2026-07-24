from __future__ import annotations

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

import architecture_verification as ARCH  # noqa: E402




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
        "partitions": [
            {
                "id": partition,
                "status": "pass",
                "inputFingerprint": fingerprint,
                "evidence": [f"bounded evidence for {partition}"],
                "findings": [],
                "discovery": _discovery_receipt(),
                "persistedContractMappings": [],
            }
            for partition in ("contract", "authority", "callers", "persistence")
        ],
        "coordinator": {
            "sessionUuid": session,
            "verdict": "PASS",
            "findingsReconciled": True,
            "persistedContractsReconciled": True,
        },
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


def test_example_adapters_cover_routed_capabilities() -> None:
    task = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    plan = MODULE.load_core(ROOT / "profiles" / "plan" / "v1.yaml")
    task_adapter = MODULE.load_adapter(
        ROOT / "examples" / "planner" / ".acdd" / "task-adapter.yaml",
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
    assert architecture["launcher"]["target"] == "pi"
    assert architecture["runtime"] not in architecture["toolEnvelope"]["admit"]
    implementation_adapter = MODULE.load_adapter(
        ROOT / "examples" / "codebase" / ".acdd" / "implementation-adapter.yaml",
        "implementation",
        task,
        allowed_root=ROOT,
    )
    review = implementation_adapter["gateProcedures"]["review/v1"]
    assert review["launcher"]["target"] == "pi_review_agents"
    assert review["launcher"]["target"] in review["toolEnvelope"]["admit"]
    for relative in (
        "examples/simple-plan/.acdd/plan-adapter.yaml",
        "examples/planner/.acdd/plan-adapter.yaml",
        "examples/linear/.acdd/plan-adapter.yaml",
        "examples/jira/.acdd/plan-adapter.yaml",
    ):
        MODULE.load_adapter(
            ROOT / relative,
            "plan",
            plan,
            allowed_root=ROOT,
        )


def test_reviewer_adapter_examples_bind_owner_roles_and_code_map_impact() -> None:
    task = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    plan = MODULE.load_core(ROOT / "profiles" / "plan" / "v1.yaml")
    reviewer_root = ROOT / "examples" / "reviewers" / ".acdd"

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
        ROOT / "examples" / "codebase" / ".acdd" / "implementation-adapter.yaml",
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
        ROOT / "examples" / "codebase" / ".acdd" / "implementation-adapter.yaml",
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


def test_capability_validation_accepts_equivalent_83b_runtime() -> None:
    core = MODULE.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    assert core.architecture_verification_schema is not None
    contract = ARCH.load_yaml(ROOT / "examples" / "task" / "architecture-verification.yaml")
    result = _verification_result(runtime="pi-review-agents")
    assert result["authoritativeSessionUuids"] == [
        "83b57c2d-75ed-4dee-9f50-e20818ab6f53"
    ]
    ARCH.validate_result(contract, core.architecture_verification_schema, result)


def test_fail_retry_requires_a_changed_fingerprint_and_plan_is_explicit() -> None:
    failed = _verification_result()
    failed["partitions"][0]["status"] = "fail"
    failed["partitions"][0]["findings"] = ["contract gap"]
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
            f"plan={ROOT / 'examples' / 'simple-plan' / '.acdd' / 'plan-adapter.yaml'}",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not list(ROOT.rglob("input-set.json"))
    assert not list(ROOT.rglob("input-spec.json"))
    assert not list(ROOT.rglob("components.json"))

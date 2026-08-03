from pathlib import Path

import pytest

from acdd.adapter import AdapterError, index_adapters, load_adapter
from acdd.model import (
    load_profile,
)


def test_task_profile_is_five_gates_and_eight_checks():
    root = Path(__file__).resolve().parents[1]
    profile = load_profile(root / "profiles" / "task" / "v1.yaml")
    assert [gate.id for gate in profile.gates] == ["design/v1", "contract/v1", "build/v1", "review/v1", "handoff/v1"]
    assert sum(len(gate.checks) for gate in profile.gates) == 8
    assert [check.id for check in profile.gates[2].checks] == ["runtime-and-integration"]
    assert profile.gates[3].review_dimensions == ("parity", "security", "code")


def test_adapter_requires_per_check_bindings(tmp_path: Path):
    path = tmp_path / "adapter.yaml"
    path.write_text("""\
apiVersion: acdd/adapter/v1
id: task
role: task
gates:
  design/v1:
    argv: [echo, no]
""", encoding="utf-8")
    with pytest.raises(AdapterError, match="only checks"):
        load_adapter(path)


def test_adapter_rejects_duplicate_roles(tmp_path: Path):
    path = tmp_path / "adapter.yaml"
    path.write_text("""\
apiVersion: acdd/adapter/v1
id: task
role: task
gates: {}
""", encoding="utf-8")
    adapter = load_adapter(path)
    with pytest.raises(AdapterError, match="duplicate adapter role"):
        index_adapters([adapter, adapter])


def test_adapter_prompt_append_is_local_and_hashed(tmp_path: Path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "runtime.md").write_text("Repository runtime context.\n", encoding="utf-8")
    path = tmp_path / "adapter.yaml"
    path.write_text(
        """apiVersion: acdd/adapter/v1
id: implementation
role: implementation
gates:
  build/v1:
    checks:
      runtime-and-integration:
        argv: [python3, -V]
        promptAppend: prompts/runtime.md
""",
        encoding="utf-8",
    )
    adapter = load_adapter(path)
    binding = adapter.gates["build/v1"].checks["runtime-and-integration"]
    assert adapter.prompt_digest(binding).startswith("sha256:")

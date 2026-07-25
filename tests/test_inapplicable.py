from __future__ import annotations

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


DOC = _load("acdd_document")
VALIDATOR = _load("validate_acdd")


def _applicability(
    *,
    engine: str = "code-map",
    evidence_ref: str = "code-map.parity",
    axes: list[str] | None = None,
    reason: str = "parity.single_backend_no_dual_store",
) -> dict[str, object]:
    return {
        "engine": engine,
        "evidenceRef": evidence_ref,
        "axesChecked": axes if axes is not None else ["deployment"],
        "reasonCode": reason,
    }


def _command_evidence(tmp_path: Path, applicability: dict[str, object]) -> str:
    (tmp_path / "source.py").write_text("value = 1\n", encoding="utf-8")
    return f"""## ACDD inputs

```yaml
apiVersion: acdd/inputs/v1
kind: inputs
paths:
  - type: source
    path: source.py
```

## ACDD gate evidence

```yaml
apiVersion: acdd/gate-evidence/v1
kind: command
id: parity.inapplicable
 gate: parity/v1
inputFingerprint: sha256:{'0' * 64}
exactCommand: code-map applicability check
recordedAt: "2026-07-24T00:00:00Z"
exitCode: 0
output: "single backend"
redacted: true
result: inapplicable
applicability:
  engine: {applicability['engine']}
  evidenceRef: {applicability['evidenceRef']}
  axesChecked: [{', '.join(applicability['axesChecked'])}]
  reasonCode: {applicability['reasonCode']}
```
""".replace(" gate: parity/v1", "gate: parity/v1")


def test_contract_allows_machine_checked_inapplicable() -> None:
    core = VALIDATOR.load_core(ROOT / "profiles" / "task" / "v1.yaml")
    assert core.receipt_contract["terminalStatuses"]["parity/v1"] == [
        "pass",
        "inapplicable",
    ]
    assert core.receipt_contract["terminalStatuses"]["security/v1"] == [
        "pass",
        "inapplicable",
    ]


def test_valid_applicability_fixture_parses_and_validates(tmp_path: Path) -> None:
    applicability = _applicability()
    parsed = DOC.parse_evidence(
        _command_evidence(tmp_path, applicability),
        workspace_root=tmp_path,
        semantic=None,
    )
    assert parsed["parity.inapplicable"].data["applicability"] == applicability
    DOC.validate_inapplicable_evidence(
        gate="parity/v1",
        applicability=applicability,
        impact_axes=frozenset({"deployment"}),
    )


@pytest.mark.parametrize(
    ("gate", "applicability", "axes", "message"),
    [
        (
            "runtime/v1",
            _applicability(),
            frozenset({"deployment"}),
            "cannot be marked inapplicable",
        ),
        (
            "parity/v1",
            _applicability(axes=[]),
            frozenset({"deployment"}),
            "expected a string list",
        ),
        (
            "parity/v1",
            _applicability(axes=["other"]),
            frozenset({"deployment"}),
            "misses impact axes",
        ),
        (
            "security/v1",
            _applicability(
                axes=["security-compliance"],
                reason="security.no_auth_identity_payload_or_egress_in_radius",
            ),
            frozenset({"security-compliance"}),
            "forbidden",
        ),
        (
            "parity/v1",
            _applicability(axes=["multi-backend-storage"]),
            frozenset({"multi-backend-storage"}),
            "forbidden",
        ),
        (
            "parity/v1",
            _applicability(
                reason="security.no_auth_identity_payload_or_egress_in_radius"
            ),
            frozenset({"deployment"}),
            "not valid for this gate",
        ),
        (
            "parity/v1",
            _applicability(reason="closed.not_allowed"),
            frozenset({"deployment"}),
            "unsupported reason code",
        ),
    ],
)
def test_inapplicable_rejects_unsafe_or_invalid_fixtures(
    gate: str,
    applicability: dict[str, object],
    axes: frozenset[str],
    message: str,
) -> None:
    with pytest.raises(DOC.DocumentError, match=message):
        DOC.validate_inapplicable_evidence(
            gate=gate,
            applicability=applicability,
            impact_axes=axes,
        )


def test_unknown_applicability_engine_is_rejected_during_evidence_parse(
    tmp_path: Path,
) -> None:
    with pytest.raises(DOC.DocumentError, match="unsupported engine"):
        DOC.parse_evidence(
            _command_evidence(tmp_path, _applicability(engine="manual")),
            workspace_root=tmp_path,
            semantic=None,
        )

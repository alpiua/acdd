"""Validate inline ACDD evidence, receipts, and task contract continuity."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from acdd_fingerprint import (
    DIGEST_RE,
    G0_BASELINE_SECTION,
    ArchitectureAmendment,
    FingerprintError,
    SemanticFingerprint,
    architecture_authority_ids,
    fingerprint_architecture_candidate,
    fingerprint_inputs,
    markdown_sections,
    parse_architecture_amendments,
    parse_inputs,
    semantic_task_fingerprint,
    yaml_documents,
)
from architecture_governor import (
    ArchitectureGovernorError,
    validate_architecture_admission,
)
from architecture_verification import (
    ArchitectureVerificationError,
)
from architecture_verification import (
    validate_result as validate_architecture_verification_result,
)
from value_domains import ValueDomain, ValueDomainError, parse_value_domains

UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
EVIDENCE_ID_RE = re.compile(r"[a-z][a-z0-9._-]+")
LEGACY_REFERENCE_RE = re.compile(r"\b(?:manifest|spec|components)=")
SECRET_RE = re.compile(
    r"(?i)(?:api[_-]?key|authorization|password|secret|token)\s*[:=]\s*(?!<redacted>)\S+"
)
NAMED_PROOFS_HEADING_RE = re.compile(r"(?m)^## Named proof IDs\s*$")
PROOF_MAPPING_HEADING_RE = re.compile(r"(?m)^## Proof obligation mapping\s*$")
PROOF_ID_RE = re.compile(r"`([a-z][a-z0-9._-]+)`")
PROOF_MAPPING_COLUMNS = (
    "Proof ID",
    "Boundary",
    "Required scenarios",
    "Execution evidence",
)
MAX_OUTPUT_BYTES = 4096
RED_STRUCTURAL_ERRORS = (
    "SyntaxError:",
    "ImportError:",
    "ModuleNotFoundError:",
    "IndentationError:",
    "NameError:",
    "AttributeError: module",
)
EXPECTED_EXCEPTION_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*(Error|Exception)$")
# Gate evidence is validated against the contract revision it was issued under.
# A task still in delivery must use the current revision, so tightening the
# contract cannot be escaped by declaring an older one; a terminal receipt keeps
# the revision it was verified against, because back-filling fields a past
# verifier never emitted would fabricate evidence.
CURRENT_EVIDENCE_REVISION = 2
SUPPORTED_EVIDENCE_REVISIONS = frozenset({1, 2})
REVISION_2_REVIEW_FIELDS = frozenset(
    {"discoveryComplete", "persistedContractChange", "persistedContractMappings"}
)


INAPPLICABLE_GATES = frozenset({"parity/v1", "security/v1"})
INAPPLICABLE_ENGINES = frozenset({"code-map", "impact-register"})
INAPPLICABLE_REASON_CODES = frozenset(
    {
        "parity.single_backend_no_dual_store",
        "security.no_auth_identity_payload_or_egress_in_radius",
    }
)
FORBIDDEN_INAPPLICABLE_AXES = frozenset(
    {"security-compliance", "multi-backend-storage", "multi-backend"}
)
INAPPLICABLE_REASON_CODES_BY_GATE = {
    "parity/v1": frozenset({"parity.single_backend_no_dual_store"}),
    "security/v1": frozenset(
        {"security.no_auth_identity_payload_or_egress_in_radius"}
    ),
}


class DocumentError(ValueError):
    """The bound task/plan inline contract is invalid."""


@dataclass(frozen=True)
class GatePolicy:
    gate: str
    terminal_statuses: frozenset[str]
    invalidation_inputs: frozenset[str]
    invalidation_classes: frozenset[str] | None = None


@dataclass(frozen=True)
class Receipt:
    gate: str
    status: str
    evidence_id: str | None
    input_fingerprint: str | None
    recorded_at: str | None


@dataclass(frozen=True)
class Evidence:
    id: str
    kind: str
    gate: str
    input_fingerprint: str
    data: dict[str, object]


@dataclass(frozen=True)
class SemanticRecord:
    sha256: str
    ids: tuple[str, ...]
    red_proof_sha256: str
    red_evidence_ids: tuple[str, ...]


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise DocumentError(f"{label}: expected a string-keyed mapping")
    return {str(key): child for key, child in value.items()}


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DocumentError(f"{label}: expected a non-empty string")
    return value.strip()


def _string_list(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise DocumentError(f"{label}: expected a string list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise DocumentError(f"{label}: expected a string list")
    result = [str(item).strip() for item in value]
    if len(result) != len(set(result)):
        raise DocumentError(f"{label}: duplicate values are not allowed")
    return result


def _bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise DocumentError(f"{label}: expected boolean")
    return value


def _proof_mapping_cells(line: str) -> tuple[str, ...]:
    if not line.startswith("|") or not line.endswith("|"):
        raise DocumentError("Proof obligation mapping rows must be Markdown table rows")
    return tuple(cell.strip() for cell in line[1:-1].split("|"))


def _validate_named_proof_coverage(text: str, proof_ids: list[str]) -> None:
    heading = NAMED_PROOFS_HEADING_RE.search(text)
    if heading is None:
        return
    next_heading = re.search(r"(?m)^## ", text[heading.end() :])
    end = heading.end() + next_heading.start() if next_heading is not None else len(text)
    missing = sorted(set(PROOF_ID_RE.findall(text[heading.end() : end])) - set(proof_ids))
    if missing:
        raise DocumentError(f"Proof obligation mapping misses named proof IDs: {missing}")


def validate_proof_obligation_mapping(text: str, *, terminal: bool) -> tuple[str, ...]:
    heading = PROOF_MAPPING_HEADING_RE.search(text)
    if heading is None:
        return ()
    next_heading = re.search(r"(?m)^## ", text[heading.end() :])
    end = heading.end() + next_heading.start() if next_heading is not None else len(text)
    lines = [line.strip() for line in text[heading.end() : end].splitlines() if line.strip()]
    if len(lines) < 3:
        raise DocumentError("Proof obligation mapping requires a header and at least one row")

    if _proof_mapping_cells(lines[0]) != PROOF_MAPPING_COLUMNS:
        raise DocumentError(
            "Proof obligation mapping columns must be Proof ID, Boundary, Required scenarios, Execution evidence"
        )
    separator = _proof_mapping_cells(lines[1])
    if len(separator) != len(PROOF_MAPPING_COLUMNS) or any(
        re.fullmatch(r":?-{3,}:?", cell) is None for cell in separator
    ):
        raise DocumentError("Proof obligation mapping separator is invalid")

    proof_ids: list[str] = []
    for index, line in enumerate(lines[2:], start=1):
        row = _proof_mapping_cells(line)
        if len(row) != len(PROOF_MAPPING_COLUMNS) or any(not cell or cell == "-" for cell in row):
            raise DocumentError(f"Proof obligation mapping row {index} is incomplete")
        row_ids = PROOF_ID_RE.findall(row[0])
        if not row_ids:
            raise DocumentError(f"Proof obligation mapping row {index} requires a backticked proof ID")
        proof_ids.extend(row_ids)
        if terminal and re.search(r"(?i)\bpending\b", row[3]):
            raise DocumentError(
                f"Proof obligation mapping row {index} remains pending at terminal review"
            )
    if len(proof_ids) != len(set(proof_ids)):
        raise DocumentError("Proof obligation mapping contains duplicate proof IDs")
    _validate_named_proof_coverage(text, proof_ids)
    return tuple(proof_ids)


def _require_keys(
    value: dict[str, object],
    *,
    required: frozenset[str],
    optional: frozenset[str],
    label: str,
) -> None:
    missing = required - set(value)
    unknown = set(value) - required - optional
    if missing or unknown:
        raise DocumentError(
            f"{label}: missing={sorted(missing)} unknown={sorted(unknown)}"
        )


def _timestamp(value: object, label: str) -> str:
    raw = _string(value, label)
    if UTC_RE.fullmatch(raw) is None:
        raise DocumentError(f"{label}: expected UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DocumentError(f"{label}: invalid UTC timestamp") from exc
    return raw


def _fingerprint(value: object, label: str) -> str:
    raw = _string(value, label)
    if DIGEST_RE.fullmatch(raw) is None:
        raise DocumentError(f"{label}: expected sha256:<64 lowercase hex>")
    return raw


def _parse_applicability(value: object, label: str) -> dict[str, object]:
    item = _mapping(value, label)
    _require_keys(
        item,
        required=frozenset({"engine", "evidenceRef", "axesChecked", "reasonCode"}),
        optional=frozenset(),
        label=label,
    )
    engine = _string(item.get("engine"), f"{label}.engine")
    if engine not in INAPPLICABLE_ENGINES:
        raise DocumentError(f"{label}.engine: unsupported engine {engine!r}")
    _string(item.get("evidenceRef"), f"{label}.evidenceRef")
    _string_list(item.get("axesChecked"), f"{label}.axesChecked")
    reason_code = _string(item.get("reasonCode"), f"{label}.reasonCode")
    if reason_code not in INAPPLICABLE_REASON_CODES:
        raise DocumentError(
            f"{label}.reasonCode: unsupported reason code {reason_code!r}"
        )
    return item


def validate_inapplicable_evidence(
    *, gate: str, applicability: object, impact_axes: frozenset[str]
) -> None:
    if gate not in INAPPLICABLE_GATES:
        raise DocumentError(f"{gate} cannot be marked inapplicable")
    item = _parse_applicability(applicability, f"{gate}.applicability")
    reason_code = _string(item.get("reasonCode"), f"{gate}.applicability.reasonCode")
    if reason_code not in INAPPLICABLE_REASON_CODES_BY_GATE[gate]:
        raise DocumentError(
            f"{gate}.applicability.reasonCode is not valid for this gate"
        )
    checked = set(item["axesChecked"])
    missing = set(impact_axes) - checked
    if missing:
        raise DocumentError(
            f"{gate}.applicability.axesChecked misses impact axes {sorted(missing)}"
        )
    normalized = {
        axis.strip().lower().replace("_", "-").replace(" ", "-")
        for axis in impact_axes
    }
    forbidden = normalized & FORBIDDEN_INAPPLICABLE_AXES
    if forbidden:
        raise DocumentError(
            f"{gate}.inapplicable is forbidden for impact axes {sorted(forbidden)}"
        )


def _parse_component_locks(
    value: object,
    *,
    declared_paths: frozenset[str],
    workspace_root: Path,
    label: str,
) -> None:
    if not isinstance(value, list) or not value:
        raise DocumentError(f"{label}: expected a non-empty component lock list")
    seen: set[str] = set()
    for index, raw in enumerate(value):
        item = _mapping(raw, f"{label}[{index}]")
        if set(item) != {"path", "sha256"}:
            raise DocumentError(f"{label}[{index}]: expected path and sha256")
        path = _string(item.get("path"), f"{label}[{index}].path")
        digest = _fingerprint(item.get("sha256"), f"{label}[{index}].sha256")
        if path in seen or path not in declared_paths:
            raise DocumentError(
                f"{label}[{index}]: duplicate or undeclared proof path {path!r}"
            )
        seen.add(path)
        target = (workspace_root / path).resolve()
        if not target.is_relative_to(workspace_root.resolve()) or not target.is_file():
            raise DocumentError(f"{label}[{index}]: missing or escaping path {path!r}")
        # The digest records the bytes observed when RED ran. The implementation
        # is expected to change those bytes, so current-worktree equality would
        # retroactively invalidate valid historical evidence.


def _evidence_revision(
    item: dict[str, object], *, active: bool, label: str
) -> int:
    raw = item.get("contractRevision", CURRENT_EVIDENCE_REVISION)
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise DocumentError(f"{label}.contractRevision: expected an integer")
    if raw not in SUPPORTED_EVIDENCE_REVISIONS:
        raise DocumentError(f"{label}.contractRevision: unsupported revision {raw}")
    if active and raw != CURRENT_EVIDENCE_REVISION:
        raise DocumentError(
            f"{label}.contractRevision: a task in delivery must issue revision "
            f"{CURRENT_EVIDENCE_REVISION}"
        )
    return raw


def parse_evidence(
    text: str,
    *,
    workspace_root: Path,
    semantic: SemanticFingerprint | None,
    active: bool = True,
) -> dict[str, Evidence]:
    sections = markdown_sections(text)
    if "ACDD gate evidence" not in sections:
        raise DocumentError("missing ## ACDD gate evidence")
    if LEGACY_REFERENCE_RE.search(sections["ACDD gate evidence"]):
        raise DocumentError(
            "legacy manifest=, spec=, and components= references are forbidden"
        )
    try:
        documents = yaml_documents(
            sections["ACDD gate evidence"], "ACDD gate evidence"
        )
        declared_paths = frozenset(item.path for item in parse_inputs(text))
    except FingerprintError as exc:
        raise DocumentError(str(exc)) from exc
    evidence: dict[str, Evidence] = {}
    if len(documents) == 1 and documents[0] == []:
        return evidence
    common = frozenset({"apiVersion", "kind", "id", "gate", "inputFingerprint"})
    schemas: dict[str, tuple[frozenset[str], frozenset[str]]] = {
        "basis": (
            common | {"summary", "authoritySources", "mappings"},
            frozenset({"contradictions"}),
        ),
        "command": (
            common
            | {
                "exactCommand",
                "recordedAt",
                "exitCode",
                "output",
                "redacted",
                "result",
            },
            frozenset(
                {
                    "gitRevision",
                    "componentLocks",
                    "proofDefinitionFingerprint",
                    "expectedException",
                    "applicability",
                }
            ),
        ),
        "review": (
            common
            | {
                "adapter",
                "sessionUuid",
                "authorSessionUuid",
                "reviewer",
                "independent",
                "terminalVerdict",
                "authoritySources",
                "productionPaths",
                "directCallers",
                "alternateCallers",
                "contradictions",
                "impactAxes",
                "matrixMappings",
                "proofMappings",
                "findings",
                "inventoryComplete",
                "decisionsResolved",
                "callerCoverageComplete",
                "persistedContractChange",
                "persistedContractMappings",
                "discoveryComplete",
            },
            frozenset(
                {
                    "verification",
                    "amendmentId",
                    "baseG0Fingerprint",
                    "codeSnapshotFingerprint",
                }
            ),
        ),
        "handoff": (
            common | {"summary", "receipts", "blockers"},
            frozenset(),
        ),
        "rationale": (
            common | {"rationale", "authorization"},
            frozenset(),
        ),
        "proof-bundle": (
            common | {"claims", "commands"},
            frozenset({"artifacts"}),
        ),
    }
    for index, raw in enumerate(documents):
        item = _mapping(raw, f"ACDD gate evidence[{index}]")
        if item.get("apiVersion") != "acdd/gate-evidence/v1":
            raise DocumentError(
                f"ACDD gate evidence[{index}]: unsupported apiVersion"
            )
        kind = _string(item.get("kind"), f"ACDD gate evidence[{index}].kind")
        if kind not in schemas:
            raise DocumentError(
                f"ACDD gate evidence[{index}]: unknown kind {kind!r}"
            )
        required, optional = schemas[kind]
        contract_revision = _evidence_revision(
            item, active=active, label=f"ACDD gate evidence[{index}]"
        )
        optional = optional | frozenset({"contractRevision"})
        if contract_revision == 1 and kind == "review":
            required = required - REVISION_2_REVIEW_FIELDS
            optional = optional | REVISION_2_REVIEW_FIELDS
        _require_keys(
            item,
            required=required,
            optional=optional,
            label=f"ACDD gate evidence[{index}]",
        )
        evidence_id = _string(item.get("id"), f"ACDD gate evidence[{index}].id")
        if EVIDENCE_ID_RE.fullmatch(evidence_id) is None:
            raise DocumentError(f"invalid evidence id {evidence_id!r}")
        if evidence_id in evidence:
            raise DocumentError(f"duplicate evidence id {evidence_id!r}")
        gate = _string(item.get("gate"), f"evidence {evidence_id}.gate")
        input_fingerprint = _fingerprint(
            item.get("inputFingerprint"),
            f"evidence {evidence_id}.inputFingerprint",
        )
        if kind == "basis":
            _string(item.get("summary"), f"evidence {evidence_id}.summary")
            _string_list(
                item.get("authoritySources"),
                f"evidence {evidence_id}.authoritySources",
            )
            _string_list(
                item.get("mappings"), f"evidence {evidence_id}.mappings"
            )
            if "contradictions" in item:
                _string_list(
                    item.get("contradictions"),
                    f"evidence {evidence_id}.contradictions",
                    allow_empty=True,
                )
        elif kind == "command":
            _string(item.get("exactCommand"), f"evidence {evidence_id}.exactCommand")
            _timestamp(item.get("recordedAt"), f"evidence {evidence_id}.recordedAt")
            if not isinstance(item.get("exitCode"), int):
                raise DocumentError(
                    f"evidence {evidence_id}.exitCode: expected integer"
                )
            output = item.get("output")
            if not isinstance(output, str):
                raise DocumentError(f"evidence {evidence_id}.output: expected string")
            if len(output.encode("utf-8")) > MAX_OUTPUT_BYTES:
                raise DocumentError(
                    f"evidence {evidence_id}.output exceeds {MAX_OUTPUT_BYTES} bytes"
                )
            if SECRET_RE.search(output):
                raise DocumentError(
                    f"evidence {evidence_id}.output contains an unredacted secret"
                )
            _bool(item.get("redacted"), f"evidence {evidence_id}.redacted")
            _string(item.get("result"), f"evidence {evidence_id}.result")
            if "applicability" in item:
                _parse_applicability(
                    item.get("applicability"),
                    f"evidence {evidence_id}.applicability",
                )
            if gate == "red/v1":
                if semantic is None:
                    raise DocumentError("red/v1 requires a semantic task fingerprint")
                proof_fingerprint = _fingerprint(
                    item.get("proofDefinitionFingerprint"),
                    f"evidence {evidence_id}.proofDefinitionFingerprint",
                )
                if proof_fingerprint != semantic.red_proof_sha256:
                    raise DocumentError(
                        f"evidence {evidence_id}: proof definition changed"
                    )
                expected_exception = _string(
                    item.get("expectedException"),
                    f"evidence {evidence_id}.expectedException",
                )
                if EXPECTED_EXCEPTION_RE.fullmatch(expected_exception) is None:
                    raise DocumentError(
                        f"evidence {evidence_id}.expectedException: invalid {expected_exception!r}"
                    )
                for struct_err in RED_STRUCTURAL_ERRORS:
                    if struct_err in output:
                        raise DocumentError(
                            f"evidence {evidence_id}: RED proof output failed with structural error ({struct_err}) rather than a domain gap expectation"
                        )
                if expected_exception not in output:
                    raise DocumentError(
                        f"evidence {evidence_id}: RED proof output does not contain expectedException {expected_exception!r}"
                    )
                revision = item.get("gitRevision")
                if revision is None:
                    _parse_component_locks(
                        item.get("componentLocks"),
                        declared_paths=declared_paths,
                        workspace_root=workspace_root,
                        label=f"evidence {evidence_id}.componentLocks",
                    )
                else:
                    _string(revision, f"evidence {evidence_id}.gitRevision")
        elif kind == "review":
            for field in (
                "adapter",
                "reviewer",
                "terminalVerdict",
            ):
                _string(item.get(field), f"evidence {evidence_id}.{field}")
            for field in ("sessionUuid", "authorSessionUuid"):
                raw_uuid = _string(item.get(field), f"evidence {evidence_id}.{field}")
                try:
                    UUID(raw_uuid)
                except ValueError as exc:
                    raise DocumentError(
                        f"evidence {evidence_id}.{field}: invalid UUID"
                    ) from exc
            for field in (
                "authoritySources",
                "productionPaths",
                "directCallers",
                "alternateCallers",
                "contradictions",
                "matrixMappings",
                "proofMappings",
                "findings",
                *(
                    ("persistedContractMappings",)
                    if contract_revision == CURRENT_EVIDENCE_REVISION
                    else ()
                ),
            ):
                _string_list(
                    item.get(field),
                    f"evidence {evidence_id}.{field}",
                    allow_empty=field
                    in {
                        "alternateCallers",
                        "contradictions",
                        "findings",
                        "persistedContractMappings",
                    },
                )
            impact = _mapping(
                item.get("impactAxes"), f"evidence {evidence_id}.impactAxes"
            )
            if not impact or not all(
                isinstance(value, str) and value.strip()
                for value in impact.values()
            ):
                raise DocumentError(
                    f"evidence {evidence_id}.impactAxes: expected non-empty string mapping"
                )
            for field in (
                "independent",
                "inventoryComplete",
                "decisionsResolved",
                "callerCoverageComplete",
                *(
                    ("persistedContractChange", "discoveryComplete")
                    if contract_revision == CURRENT_EVIDENCE_REVISION
                    else ()
                ),
            ):
                _bool(item.get(field), f"evidence {evidence_id}.{field}")
            architecture_fingerprint_fields = {
                "baseG0Fingerprint",
                "codeSnapshotFingerprint",
            }
            present_architecture_fields = architecture_fingerprint_fields & set(item)
            if present_architecture_fields and present_architecture_fields != architecture_fingerprint_fields:
                raise DocumentError(
                    f"evidence {evidence_id}: baseG0Fingerprint and "
                    "codeSnapshotFingerprint must appear together"
                )
            if present_architecture_fields:
                _fingerprint(
                    item.get("baseG0Fingerprint"),
                    f"evidence {evidence_id}.baseG0Fingerprint",
                )
                _fingerprint(
                    item.get("codeSnapshotFingerprint"),
                    f"evidence {evidence_id}.codeSnapshotFingerprint",
                )
            if "amendmentId" in item:
                amendment_id = _string(
                    item.get("amendmentId"), f"evidence {evidence_id}.amendmentId"
                )
                if EVIDENCE_ID_RE.fullmatch(amendment_id) is None:
                    raise DocumentError(
                        f"evidence {evidence_id}.amendmentId: invalid identifier"
                    )
                if not present_architecture_fields:
                    raise DocumentError(
                        f"evidence {evidence_id}: amendment review requires "
                        "baseG0Fingerprint and codeSnapshotFingerprint"
                    )
        elif kind == "handoff":
            _string(item.get("summary"), f"evidence {evidence_id}.summary")
            _string_list(item.get("receipts"), f"evidence {evidence_id}.receipts")
            _string_list(
                item.get("blockers"),
                f"evidence {evidence_id}.blockers",
                allow_empty=True,
            )
        elif kind == "proof-bundle":
            claims = _string_list(
                item.get("claims"), f"evidence {evidence_id}.claims"
            )
            if gate not in claims:
                raise DocumentError(
                    f"evidence {evidence_id}: gate must be one of claims"
                )
            commands = item.get("commands")
            if not isinstance(commands, list) or not commands:
                raise DocumentError(
                    f"evidence {evidence_id}.commands: expected a non-empty list"
                )
            for cmd_index, raw_command in enumerate(commands):
                command = _mapping(
                    raw_command, f"evidence {evidence_id}.commands[{cmd_index}]"
                )
                _require_keys(
                    command,
                    required=frozenset(
                        {
                            "exactCommand",
                            "recordedAt",
                            "exitCode",
                            "output",
                            "redacted",
                            "result",
                        }
                    ),
                    optional=frozenset(),
                    label=f"evidence {evidence_id}.commands[{cmd_index}]",
                )
                _string(
                    command.get("exactCommand"),
                    f"evidence {evidence_id}.commands[{cmd_index}].exactCommand",
                )
                _timestamp(
                    command.get("recordedAt"),
                    f"evidence {evidence_id}.commands[{cmd_index}].recordedAt",
                )
                if not isinstance(command.get("exitCode"), int):
                    raise DocumentError(
                        f"evidence {evidence_id}.commands[{cmd_index}].exitCode: "
                        "expected integer"
                    )
                output = command.get("output")
                if not isinstance(output, str):
                    raise DocumentError(
                        f"evidence {evidence_id}.commands[{cmd_index}].output: "
                        "expected string"
                    )
                if len(output.encode("utf-8")) > MAX_OUTPUT_BYTES:
                    raise DocumentError(
                        f"evidence {evidence_id}.commands[{cmd_index}].output "
                        f"exceeds {MAX_OUTPUT_BYTES} bytes"
                    )
                if SECRET_RE.search(output):
                    raise DocumentError(
                        f"evidence {evidence_id}.commands[{cmd_index}].output "
                        "contains an unredacted secret"
                    )
                _bool(
                    command.get("redacted"),
                    f"evidence {evidence_id}.commands[{cmd_index}].redacted",
                )
                _string(
                    command.get("result"),
                    f"evidence {evidence_id}.commands[{cmd_index}].result",
                )
            if "artifacts" in item:
                artifacts = item.get("artifacts")
                if not isinstance(artifacts, list):
                    raise DocumentError(
                        f"evidence {evidence_id}.artifacts: expected a list"
                    )
                for art_index, raw_artifact in enumerate(artifacts):
                    if not isinstance(raw_artifact, str) or not raw_artifact.strip():
                        raise DocumentError(
                            f"evidence {evidence_id}.artifacts[{art_index}]: "
                            "expected non-empty string"
                        )
        else:
            _string(item.get("rationale"), f"evidence {evidence_id}.rationale")
            _string(item.get("authorization"), f"evidence {evidence_id}.authorization")
        evidence[evidence_id] = Evidence(
            id=evidence_id,
            kind=kind,
            gate=gate,
            input_fingerprint=input_fingerprint,
            data=item,
        )
    return evidence


def parse_receipts(text: str, *, plan: bool) -> tuple[Receipt, ...]:
    sections = markdown_sections(text)
    names = ("ACDD plan receipts", "ACDD receipts") if plan else ("ACDD receipts",)
    section_name = next((name for name in names if name in sections), None)
    if section_name is None:
        raise DocumentError(f"missing ## {names[0]}")
    body = sections[section_name]
    if LEGACY_REFERENCE_RE.search(body):
        raise DocumentError(
            "legacy manifest=, spec=, and components= references are forbidden"
        )
    rows: list[Receipt] = []
    for line in body.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5 or cells[0].lower() == "gate" or set(cells[0]) <= {"-", ":"}:
            continue
        gate, status, evidence_raw, fingerprint_raw, recorded_raw = cells[:5]
        evidence_id: str | None = None
        if evidence_raw != "pending":
            match = re.fullmatch(r"evidence=([a-z][a-z0-9._-]+)", evidence_raw)
            if match is None:
                raise DocumentError(
                    f"receipt {gate}: evidence must be pending or evidence=<id>"
                )
            evidence_id = match.group(1)
        input_fingerprint = (
            None
            if fingerprint_raw == "pending"
            else _fingerprint(fingerprint_raw, f"receipt {gate}.inputFingerprint")
        )
        recorded_at = (
            None
            if recorded_raw == "pending"
            else _timestamp(recorded_raw, f"receipt {gate}.recordedAt")
        )
        rows.append(
            Receipt(gate, status, evidence_id, input_fingerprint, recorded_at)
        )
    if not rows:
        raise DocumentError(f"{section_name}: no receipt rows")
    if len({row.gate for row in rows}) != len(rows):
        raise DocumentError("duplicate receipt gate")
    return tuple(rows)


def parse_semantic_record(text: str) -> SemanticRecord:
    sections = markdown_sections(text)
    if "ACDD contract fingerprint" not in sections:
        raise DocumentError("active task missing ## ACDD contract fingerprint")
    try:
        documents = yaml_documents(
            sections["ACDD contract fingerprint"], "ACDD contract fingerprint"
        )
    except FingerprintError as exc:
        raise DocumentError(str(exc)) from exc
    if len(documents) != 1:
        raise DocumentError("ACDD contract fingerprint: expected one document")
    item = _mapping(documents[0], "ACDD contract fingerprint")
    required = frozenset(
        {
            "apiVersion",
            "sha256",
            "ids",
            "redProofFingerprint",
            "redEvidenceIds",
        }
    )
    _require_keys(
        item,
        required=required,
        optional=frozenset(),
        label="ACDD contract fingerprint",
    )
    if item.get("apiVersion") != "acdd/semantic-fingerprint/v1":
        raise DocumentError("unsupported semantic fingerprint apiVersion")
    return SemanticRecord(
        sha256=_fingerprint(item.get("sha256"), "semantic fingerprint.sha256"),
        ids=tuple(
            _string_list(
                item.get("ids"), "semantic fingerprint.ids", allow_empty=True
            )
        ),
        red_proof_sha256=_fingerprint(
            item.get("redProofFingerprint"),
            "semantic fingerprint.redProofFingerprint",
        ),
        red_evidence_ids=tuple(
            _string_list(
                item.get("redEvidenceIds"),
                "semantic fingerprint.redEvidenceIds",
                allow_empty=True,
            )
        ),
    )


def _validate_architecture_amendments(
    *,
    text: str,
    document: Path,
    workspace_root: Path,
    amendments: tuple[ArchitectureAmendment, ...],
    semantic_record: SemanticRecord | None,
    receipts: tuple[Receipt, ...],
    evidence: dict[str, Evidence],
    expected_value_domain_ids: set[str],
    architecture_verification_schema: dict[str, object] | None,
    architecture_verification_contract: dict[str, object] | None,
    reviewing_amendment: str | None = None,
) -> None:
    if not amendments:
        if reviewing_amendment is not None:
            raise DocumentError(
                f"unknown pending architecture amendment {reviewing_amendment!r}"
            )
        return
    if semantic_record is None:
        raise DocumentError("G1 redesign amendments require an active G0 fingerprint")
    receipt_map = {receipt.gate: receipt for receipt in receipts}
    architecture_receipt = receipt_map.get("architecture/v1")
    if architecture_receipt is None or architecture_receipt.status != "pass":
        raise DocumentError("G1 redesign amendments require a terminal G0 architecture PASS")
    unresolved: list[str] = []
    for amendment in amendments:
        if amendment.base_g0_fingerprint != semantic_record.sha256:
            raise DocumentError(
                f"amendment {amendment.id}: baseG0Fingerprint does not match "
                "the frozen G0 baseline"
            )
        review = amendment.review
        status = _string(review.get("status"), f"amendment {amendment.id}.review.status")
        if amendment.receipt_path is not None:
            if status == "pending":
                if any(
                    review.get(field) != "pending"
                    for field in (
                        "receiptSha256",
                        "transcriptSha256",
                        "inputFingerprint",
                        "recordedAt",
                    )
                ):
                    raise DocumentError(
                        f"amendment {amendment.id}: pending review must use pending terminal values"
                    )
                unresolved.append(amendment.id)
                continue
            if status not in {"pass", "fail", "blocked"}:
                raise DocumentError(
                    f"amendment {amendment.id}.review.status: expected pending, pass, fail, or blocked"
                )
            _fingerprint(
                review.get("receiptSha256"),
                f"amendment {amendment.id}.review.receiptSha256",
            )
            _fingerprint(
                review.get("transcriptSha256"),
                f"amendment {amendment.id}.review.transcriptSha256",
            )
            input_fingerprint = _fingerprint(
                review.get("inputFingerprint"),
                f"amendment {amendment.id}.review.inputFingerprint",
            )
            _timestamp(
                review.get("recordedAt"), f"amendment {amendment.id}.review.recordedAt"
            )
            if status == "pass" and input_fingerprint != amendment.fingerprint:
                raise DocumentError(
                    f"amendment {amendment.id}: stale supplemental architecture fingerprint"
                )
            if status != "pass":
                unresolved.append(amendment.id)
            continue
        else:
            if status == "pending":
                if any(
                    review.get(field) != "pending"
                    for field in ("evidence", "inputFingerprint", "recordedAt")
                ):
                    raise DocumentError(
                        f"amendment {amendment.id}: pending review must contain only pending values"
                    )
                unresolved.append(amendment.id)
                continue
            if status != "pass":
                raise DocumentError(
                    f"amendment {amendment.id}.review.status: expected pending or pass"
                )
            evidence_id = _string(
                review.get("evidence"), f"amendment {amendment.id}.review.evidence"
            )
            input_fingerprint = _fingerprint(
                review.get("inputFingerprint"),
                f"amendment {amendment.id}.review.inputFingerprint",
            )
            _timestamp(
                review.get("recordedAt"), f"amendment {amendment.id}.review.recordedAt"
            )
            if input_fingerprint != amendment.fingerprint:
                raise DocumentError(
                    f"amendment {amendment.id}: stale supplemental architecture fingerprint"
                )
            review_evidence = evidence.get(evidence_id)
            if review_evidence is None:
                raise DocumentError(
                    f"amendment {amendment.id}: missing evidence {evidence_id!r}"
                )
            data = review_evidence.data
            if (
                review_evidence.kind != "review"
                or review_evidence.gate != "architecture-amendment/v1"
                or review_evidence.input_fingerprint != amendment.fingerprint
                or data.get("amendmentId") != amendment.id
                or data.get("baseG0Fingerprint") != amendment.base_g0_fingerprint
                or data.get("terminalVerdict") != "PASS"
                or data.get("independent") is not True
                or data.get("sessionUuid") == data.get("authorSessionUuid")
            ):
                raise DocumentError(
                    f"amendment {amendment.id}: invalid supplemental architecture review"
                )
            verification = data.get("verification")
        if (
            not isinstance(verification, dict)
            or verification.get("inputFingerprint") != amendment.fingerprint
            or architecture_verification_schema is None
            or architecture_verification_contract is None
        ):
            raise DocumentError(
                f"amendment {amendment.id}: missing routed verification result"
            )
        try:
            validate_architecture_verification_result(
                architecture_verification_contract,
                architecture_verification_schema,
                verification,
                expected_value_domain_ids=expected_value_domain_ids,
            )
        except ArchitectureVerificationError as exc:
            raise DocumentError(str(exc)) from exc
    if reviewing_amendment is not None:
        selected = next(
            (item for item in amendments if item.id == reviewing_amendment), None
        )
        if selected is None:
            raise DocumentError(
                f"unknown pending architecture amendment {reviewing_amendment!r}"
            )
        if selected.id not in unresolved:
            raise DocumentError(
                f"architecture amendment {reviewing_amendment!r} is not reviewable"
            )
    if unresolved and reviewing_amendment is None:
        for gate in (
            "runtime/v1",
            "parity/v1",
            "security/v1",
            "release/v1",
            "review/v1",
            "handoff/v1",
        ):
            receipt = receipt_map.get(gate)
            if receipt is not None and receipt.status not in {"pending", "blocked"}:
                raise DocumentError(
                    f"unreviewed architecture amendments {unresolved} block {gate}"
                )
def _architecture_freshness_basis(
    *,
    text: str,
    semantic: SemanticFingerprint | None,
    gate_evidence: Evidence,
    receipt: Receipt,
    candidate_fingerprint: str,
    legacy_code_fingerprint: str,
) -> frozenset[str]:
    if (
        G0_BASELINE_SECTION in markdown_sections(text)
        and semantic is not None
        and gate_evidence.data.get("baseG0Fingerprint") == semantic.sha256
        and gate_evidence.data.get("codeSnapshotFingerprint") is not None
        and receipt.input_fingerprint is not None
    ):
        return frozenset({receipt.input_fingerprint})
    return frozenset({candidate_fingerprint, legacy_code_fingerprint})


def _validate_contract_changes(
    text: str,
    *,
    current: SemanticFingerprint,
    record: SemanticRecord,
    receipts: tuple[Receipt, ...],
    gate_order: tuple[str, ...],
) -> None:
    sections = markdown_sections(text)
    if (
        record.sha256 == current.sha256
        and record.ids == current.ids
    ):
        return
    if "ACDD contract changes" not in sections:
        raise DocumentError("semantic contract changed without contract-change chain")
    try:
        documents = yaml_documents(
            sections["ACDD contract changes"], "ACDD contract changes"
        )
    except FingerprintError as exc:
        raise DocumentError(str(exc)) from exc
    if not documents:
        raise DocumentError("empty contract-change chain")
    accepted = False
    for index, raw in enumerate(documents):
        item = _mapping(raw, f"contract change[{index}]")
        if item.get("apiVersion") != "acdd/contract-change/v1":
            raise DocumentError(f"contract change[{index}]: unsupported apiVersion")
        kind = _string(item.get("kind"), f"contract change[{index}].kind")
        if kind == "profile-migration":
            required = frozenset(
                {
                    "apiVersion",
                    "kind",
                    "beforeFingerprint",
                    "afterFingerprint",
                    "beforeIds",
                    "afterIds",
                }
            )
            _require_keys(
                item,
                required=required,
                optional=frozenset(),
                label=f"contract change[{index}]",
            )
            before = _fingerprint(
                item.get("beforeFingerprint"), f"contract change[{index}].before"
            )
            after = _fingerprint(
                item.get("afterFingerprint"), f"contract change[{index}].after"
            )
            before_ids = set(
                _string_list(item.get("beforeIds"), f"contract change[{index}].beforeIds", allow_empty=True)
            )
            after_ids = set(
                _string_list(item.get("afterIds"), f"contract change[{index}].afterIds", allow_empty=True)
            )
            if before != after or after != current.sha256 or before_ids - after_ids:
                raise DocumentError(
                    "profile-migration must preserve semantic fingerprint and IDs: "
                    f"before={before} after={after} current={current.sha256} "
                    f"removedIds={sorted(before_ids - after_ids)}"
                )
            accepted = True
        elif kind == "semantic-change":
            required = frozenset(
                {
                    "apiVersion",
                    "kind",
                    "rationale",
                    "authorization",
                    "beforeFingerprint",
                    "afterFingerprint",
                    "removedIds",
                }
            )
            _require_keys(
                item,
                required=required,
                optional=frozenset(),
                label=f"contract change[{index}]",
            )
            _string(item.get("rationale"), f"contract change[{index}].rationale")
            _string(item.get("authorization"), f"contract change[{index}].authorization")
            before = _fingerprint(
                item.get("beforeFingerprint"), f"contract change[{index}].before"
            )
            after = _fingerprint(
                item.get("afterFingerprint"), f"contract change[{index}].after"
            )
            removed = set(
                _string_list(item.get("removedIds"), f"contract change[{index}].removedIds", allow_empty=True)
            )
            actual_removed = set(record.ids) - set(current.ids)
            if before != record.sha256 or after != current.sha256 or removed != actual_removed:
                raise DocumentError(
                    "semantic-change fingerprints or explicit removed IDs do not match: "
                    f"record={record.sha256} before={before} current={current.sha256} "
                    f"after={after} removed={sorted(removed)} "
                    f"actualRemoved={sorted(actual_removed)}"
                )
            reset_from = gate_order.index("matrix/v1")
            receipt_map = {receipt.gate: receipt for receipt in receipts}
            for gate in gate_order[reset_from:]:
                if receipt_map[gate].status not in {"pending", "blocked"}:
                    raise DocumentError(
                        f"semantic-change requires nonterminal receipt {gate}"
                    )
            accepted = True
        else:
            raise DocumentError(f"contract change[{index}]: unknown kind {kind!r}")
    if not accepted:
        raise DocumentError("current semantic change lacks an authorized semantic-change record")


def validate_document(
    *,
    document: Path,
    profile: Path,
    receipt_contract: Path,
    adapters: tuple[Path, ...],
    workspace_root: Path,
    policies: tuple[GatePolicy, ...],
    plan: bool,
    impact_axes: frozenset[str],
    architecture_verification_schema: dict[str, object] | None = None,
    architecture_verification_contract: dict[str, object] | None = None,
    reviewing_amendment: str | None = None,
) -> None:
    text = document.read_text(encoding="utf-8")
    if LEGACY_REFERENCE_RE.search(text):
        raise DocumentError(
            "legacy manifest=, spec=, and components= references are forbidden"
        )
    semantic: SemanticFingerprint | None = None
    semantic_record: SemanticRecord | None = None
    active = False
    if not plan:
        try:
            semantic = semantic_task_fingerprint(text)
        except FingerprintError as exc:
            raise DocumentError(str(exc)) from exc
        frontmatter = text.split("---", 2)[1] if text.startswith("---") else ""
        active = bool(re.search(r"(?m)^status:\s*(?:in_progress|active)\s*$", frontmatter))
        if active:
            semantic_record = parse_semantic_record(text)
    try:
        declared_paths = frozenset(item.path for item in parse_inputs(text))
        value_domains: tuple[ValueDomain, ...] = (
            ()
            if plan or semantic is None
            else parse_value_domains(
                text,
                workspace_root=workspace_root,
                declared_paths=declared_paths,
                semantic_ids=frozenset(architecture_authority_ids(text)),
            )
        )
    except (FingerprintError, ValueDomainError) as exc:
        raise DocumentError(str(exc)) from exc
    evidence = parse_evidence(
        text,
        workspace_root=workspace_root,
        semantic=semantic,
        active=active,
    )
    receipts = parse_receipts(text, plan=plan)
    try:
        amendments = () if plan else parse_architecture_amendments(text)
    except FingerprintError as exc:
        raise DocumentError(str(exc)) from exc
    _validate_architecture_amendments(
        text=text,
        document=document,
        workspace_root=workspace_root,
        amendments=amendments,
        semantic_record=semantic_record,
        receipts=receipts,
        evidence=evidence,
        expected_value_domain_ids={domain.id for domain in value_domains},
        architecture_verification_schema=architecture_verification_schema,
        architecture_verification_contract=architecture_verification_contract,
        reviewing_amendment=reviewing_amendment,
    )
    policy_map = {policy.gate: policy for policy in policies}
    receipt_map = {receipt.gate: receipt for receipt in receipts}
    if set(receipt_map) != set(policy_map):
        raise DocumentError(
            f"receipt gates mismatch: expected={list(policy_map)} found={list(receipt_map)}"
        )
    if not plan:
        proof_mapping_terminal = any(
            gate in policy_map
            and gate in receipt_map
            and receipt_map[gate].status in policy_map[gate].terminal_statuses
            for gate in ("review/v1", "handoff/v1")
        )
        validate_proof_obligation_mapping(text, terminal=proof_mapping_terminal)
    gate_order = tuple(policy_map)
    g0_frozen = (
        semantic_record is not None
        and receipt_map.get("architecture/v1") is not None
        and receipt_map["architecture/v1"].status == "pass"
    )
    seen_evidence: set[str] = set()
    terminal_seen = True
    for policy in policies:
        receipt = receipt_map[policy.gate]
        allowed_statuses = {"pending", "blocked"} | set(policy.terminal_statuses)
        if receipt.status not in allowed_statuses:
            raise DocumentError(
                f"receipt {policy.gate}: invalid status {receipt.status!r}"
            )
        if receipt.status == "pending":
            if any(
                value is not None
                for value in (
                    receipt.evidence_id,
                    receipt.input_fingerprint,
                    receipt.recorded_at,
                )
            ):
                raise DocumentError(
                    f"receipt {policy.gate}: pending row must contain only pending values"
                )
            terminal_seen = False
            continue
        if (
            receipt.evidence_id is None
            or receipt.input_fingerprint is None
            or receipt.recorded_at is None
        ):
            raise DocumentError(
                f"receipt {policy.gate}: nonpending status requires complete inline evidence"
            )
        gate_evidence = evidence.get(receipt.evidence_id)
        if gate_evidence is None:
            raise DocumentError(
                f"receipt {policy.gate}: missing evidence {receipt.evidence_id!r}"
            )
        if receipt.evidence_id in seen_evidence:
            if gate_evidence.kind != "proof-bundle":
                raise DocumentError(
                    f"evidence {receipt.evidence_id!r} cannot satisfy multiple receipts"
                )
        else:
            seen_evidence.add(receipt.evidence_id)
        if gate_evidence.kind == "proof-bundle":
            claims = gate_evidence.data.get("claims")
            if not isinstance(claims, list) or policy.gate not in claims:
                raise DocumentError(
                    f"evidence {gate_evidence.id}: claims do not cover receipt {policy.gate}"
                )
            unknown_claims = [claim for claim in claims if claim not in policy_map]
            if unknown_claims:
                raise DocumentError(
                    f"evidence {gate_evidence.id}: unknown claim gates {unknown_claims}"
                )
            if len(claims) != len(set(claims)):
                raise DocumentError(
                    f"evidence {gate_evidence.id}: claims must be unique"
                )
        elif gate_evidence.gate != policy.gate:
            raise DocumentError(
                f"evidence {gate_evidence.id}: gate does not match receipt"
            )
        current_inputs = policy.invalidation_inputs
        current_classes = policy.invalidation_classes
        if gate_evidence.kind == "proof-bundle":
            claims = gate_evidence.data.get("claims")
            if not isinstance(claims, list):
                raise DocumentError(
                    f"evidence {gate_evidence.id}: claims must be a list"
                )
            current_inputs = frozenset(
                input_type
                for claim in claims
                for input_type in policy_map[claim].invalidation_inputs
            )
            class_sets = [
                policy_map[claim].invalidation_classes
                for claim in claims
                if policy_map[claim].invalidation_classes is not None
            ]
            current_classes = (
                frozenset().union(*(classes or frozenset() for classes in class_sets))
                if class_sets
                else None
            )
        legacy_architecture_fingerprint: str | None = None
        if policy.gate == "architecture/v1":
            architecture_candidate = fingerprint_architecture_candidate(
                document=document,
                adapters=adapters,
                workspace_root=workspace_root,
            )
            current = architecture_candidate.sha256
            legacy_architecture_fingerprint = architecture_candidate.code_sha256
            architecture_freshness = _architecture_freshness_basis(
                text=text,
                semantic=semantic,
                gate_evidence=gate_evidence,
                receipt=receipt,
                candidate_fingerprint=current,
                legacy_code_fingerprint=legacy_architecture_fingerprint,
            )
            if receipt.input_fingerprint in architecture_freshness:
                current = receipt.input_fingerprint or current
        else:
            current = fingerprint_inputs(
                document=document,
                profile=profile,
                receipt_contract=receipt_contract,
                adapters=adapters,
                workspace_root=workspace_root,
                include_types=current_inputs,
                include_classes=current_classes,
            ).sha256
        # Normal delivery validates every terminal receipt against current inputs.
        # Supplemental amendment review instead validates the selected amendment
        # against its frozen G0 fingerprint; historical receipt bytes remain
        # evidence and must still agree with their receipt, but are not its admission
        # snapshot. This lets redesign review precede downstream receipt refresh.
        if (
            gate_evidence.input_fingerprint != receipt.input_fingerprint
            or (
                active
                and not (
                    g0_frozen
                    and policy.gate in {"matrix/v1", "architecture/v1"}
                )
                and (
                    reviewing_amendment is None
                    or policy.gate not in {"matrix/v1", "architecture/v1"}
                )
                and receipt.input_fingerprint
                not in {current, legacy_architecture_fingerprint}
            )
        ):
            expected = current
            if legacy_architecture_fingerprint is not None:
                expected += f" or legacy {legacy_architecture_fingerprint}"
            raise DocumentError(
                f"receipt {policy.gate}: stale input fingerprint; expected {expected}, "
                f"found {receipt.input_fingerprint}"
            )
        if receipt.status in policy.terminal_statuses and not terminal_seen:
            raise DocumentError(
                f"receipt {policy.gate}: later gate cannot be terminal before predecessors"
            )
        expected_kinds: dict[str, frozenset[str]] = {
            "matrix/v1": frozenset({"basis"}),
            "architecture-light/v1": frozenset({"basis"}),
            "architecture/v1": frozenset({"review"}),
            "red/v1": frozenset({"command", "rationale"}),
            "runtime/v1": frozenset({"command", "proof-bundle"}),
            "parity/v1": frozenset({"command", "proof-bundle"}),
            "security/v1": frozenset({"command", "proof-bundle"}),
            "release/v1": frozenset({"command", "proof-bundle"}),
            "review/v1": frozenset({"review"}),
            "handoff/v1": frozenset({"handoff"}),
            "intent/v1": frozenset({"basis"}),
            "evidence/v1": frozenset({"basis"}),
            "plan-shape/v1": frozenset({"basis"}),
            "roadmap-shape/v1": frozenset({"basis", "rationale"}),
            "milestone-shape/v1": frozenset({"basis", "rationale"}),
            "decomposition/v1": frozenset({"basis"}),
        }
        allowed_kinds = expected_kinds.get(policy.gate, frozenset({"command"}))
        if gate_evidence.kind not in allowed_kinds:
            raise DocumentError(
                f"evidence {gate_evidence.id}: kind {gate_evidence.kind!r} cannot satisfy {policy.gate}"
            )
        applicability = gate_evidence.data.get("applicability")
        if receipt.status == "inapplicable":
            if gate_evidence.kind != "command":
                raise DocumentError(
                    f"receipt {policy.gate}: inapplicable requires command evidence"
                )
            if applicability is None:
                raise DocumentError(
                    f"receipt {policy.gate}: inapplicable requires applicability evidence"
                )
            validate_inapplicable_evidence(
                gate=policy.gate,
                applicability=applicability,
                impact_axes=impact_axes,
            )
        elif applicability is not None:
            raise DocumentError(
                f"evidence {gate_evidence.id}: applicability is only valid for inapplicable status"
            )
        if (
            policy.gate == "matrix/v1"
            and receipt.status in policy.terminal_statuses
            and value_domains
        ):
            mappings = gate_evidence.data.get("mappings")
            missing = {domain.id for domain in value_domains} - set(
                mappings if isinstance(mappings, list) else []
            )
            if missing:
                raise DocumentError(
                    f"matrix/v1 evidence misses persisted contracts {sorted(missing)}"
                )
        if receipt.status in policy.terminal_statuses and gate_evidence.kind == "review":
            review = gate_evidence.data
            verdict = review.get("terminalVerdict")
            if verdict != "PASS":
                raise DocumentError(
                    f"receipt {policy.gate}: terminal pass requires review verdict PASS"
                )
            if review.get("independent") is not True or review.get(
                "sessionUuid"
            ) == review.get("authorSessionUuid"):
                raise DocumentError(
                    f"receipt {policy.gate}: invalid independent-session provenance"
                )
            if policy.gate == "architecture/v1" and not plan:
                expected_value_domain_ids = {domain.id for domain in value_domains}
                for field in (
                    "inventoryComplete",
                    "decisionsResolved",
                    "callerCoverageComplete",
                ):
                    if review.get(field) is not True:
                        raise DocumentError(
                            f"architecture/v1 pass requires {field}"
                        )
                contradictions = review.get("contradictions")
                if contradictions != []:
                    raise DocumentError(
                        "architecture/v1 pass requires no unresolved contradictions"
                    )
                if (
                    gate_evidence.data.get(
                        "contractRevision", CURRENT_EVIDENCE_REVISION
                    )
                    == CURRENT_EVIDENCE_REVISION
                ):
                    if review.get("discoveryComplete") is not True:
                        raise DocumentError(
                            "architecture/v1 pass requires discoveryComplete"
                        )
                    if review.get("persistedContractChange") is not bool(value_domains):
                        raise DocumentError(
                            "architecture/v1 persistedContractChange contradicts the persisted-contract matrix"
                        )
                    value_domain_mappings = review.get("persistedContractMappings")
                    if (
                        not isinstance(value_domain_mappings, list)
                        or set(value_domain_mappings) != expected_value_domain_ids
                        or len(value_domain_mappings) != len(expected_value_domain_ids)
                    ):
                        raise DocumentError(
                            "architecture/v1 persistedContractMappings must exactly cover the persisted-contract matrix"
                        )
                axes = review.get("impactAxes")
                if not isinstance(axes, dict) or not impact_axes <= set(axes):
                    raise DocumentError(
                        "architecture/v1 pass lacks adapter impact-axis coverage"
                    )
                for field in (
                    "authoritySources",
                    "productionPaths",
                    "directCallers",
                    "matrixMappings",
                    "proofMappings",
                ):
                    value = review.get(field)
                    if not isinstance(value, list) or not value:
                        raise DocumentError(
                            f"architecture/v1 pass requires {field}"
                        )
                verification = review.get("verification")
                if not isinstance(verification, dict):
                    raise DocumentError(
                        "architecture/v1 pass requires capability-based verification evidence"
                    )
                if architecture_verification_schema is None or architecture_verification_contract is None:
                    raise DocumentError(
                        "architecture/v1 pass requires the routed verification contract"
                    )
                if verification.get("inputFingerprint") != gate_evidence.input_fingerprint:
                    raise DocumentError(
                        "architecture/v1 verification fingerprint does not match gate evidence"
                    )
                # Revision 1 predates the persisted-contract axis and the current
                # partition names, so its result was verified against a schema that
                # no longer exists. It keeps the verdict it was issued with; only a
                # fresh architecture/v1 run can produce a revision 2 result.
                if gate_evidence.data.get("contractRevision", CURRENT_EVIDENCE_REVISION) == CURRENT_EVIDENCE_REVISION:
                    try:
                        verification_context = verification.get("reviewContext")
                        verification_coverage = (
                            {
                                path
                                for item in verification_context.get("coverageFiles", [])
                                if isinstance(item, dict)
                                for path in (item.get("path"), item.get("repositoryPath"))
                                if isinstance(path, str) and path.strip()
                            }
                            if isinstance(verification_context, dict)
                            else None
                        )
                        verification_path_contract = (
                            verification_context.get("pathContract")
                            if isinstance(verification_context, dict)
                            else None
                        )
                        verification_repository_root = (
                            verification_path_contract.get(
                                "implementationRepositoryRoot",
                                verification_path_contract.get("workspaceRoot"),
                            )
                            if isinstance(verification_path_contract, dict)
                            else None
                        )
                        validate_architecture_verification_result(
                            architecture_verification_contract,
                            architecture_verification_schema,
                            verification,
                            expected_value_domain_ids=expected_value_domain_ids,
                            expected_document=document,
                            expected_task_paths={
                                document.as_posix(),
                                document.relative_to(workspace_root).as_posix(),
                                document.name,
                            },
                            expected_repository_root=verification_repository_root,
                            expected_coverage_paths=verification_coverage,
                        )
                    except ArchitectureVerificationError as exc:
                        raise DocumentError(str(exc)) from exc
                if not g0_frozen:
                    try:
                        validate_architecture_admission(
                            text=text,
                            workspace_root=workspace_root,
                            architecture_fingerprint=gate_evidence.input_fingerprint,
                        )
                    except ArchitectureGovernorError as exc:
                        raise DocumentError(
                            f"architecture/v1 admission failed: {exc}"
                        ) from exc
        if receipt.status == "blocked" or receipt.status not in policy.terminal_statuses:
            terminal_seen = False
    if semantic is not None and semantic_record is not None:
        if reviewing_amendment is None:
            _validate_contract_changes(
                text,
                current=semantic,
                record=semantic_record,
                receipts=receipts,
                gate_order=gate_order,
            )
        if any(
            evidence_id not in evidence
            or evidence[evidence_id].gate != "red/v1"
            for evidence_id in semantic_record.red_evidence_ids
        ):
            raise DocumentError(
                "active task cannot lose its recorded RED evidence"
            )

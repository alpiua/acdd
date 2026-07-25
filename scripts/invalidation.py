"""Dependency-aware ACDD receipt invalidation planning.

Fingerprints remain authoritative. This module only computes the smallest
ordered set of gates that must be rerun after typed input changes; unknown
input classes fail closed by invalidating every gate and its successors.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml


class InvalidationError(ValueError):
    """Invalid dependency graph or ambiguous changed-input classification."""


@dataclass(frozen=True)
class ChangedInput:
    type: str
    path: str
    classes: frozenset[str] | None = None


@dataclass(frozen=True)
class InvalidationPolicy:
    gate: str
    input_types: frozenset[str]
    classes: frozenset[str] | None = None


def load_contract(path: Path) -> dict[str, object]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise InvalidationError(f"cannot load receipt contract {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise InvalidationError("receipt contract must be a mapping")
    return value


def validate_graph(
    graph: Mapping[str, object], gate_ids: tuple[str, ...] | list[str]
) -> dict[str, tuple[str, ...]]:
    expected = set(gate_ids)
    if set(graph) != expected:
        raise InvalidationError(
            f"successorInvalidation gates must exactly match profile: "
            f"expected={sorted(expected)} found={sorted(graph)}"
        )
    result: dict[str, tuple[str, ...]] = {}
    for gate in gate_ids:
        raw = graph[gate]
        if not isinstance(raw, (list, tuple)) or not all(
            isinstance(item, str) and item.strip() for item in raw
        ):
            raise InvalidationError(
                f"successorInvalidation.{gate}: expected string list"
            )
        values = tuple(raw)
        if len(values) != len(set(values)):
            raise InvalidationError(f"successorInvalidation.{gate}: duplicate successor")
        unknown = set(values) - expected
        if unknown:
            raise InvalidationError(
                f"successorInvalidation.{gate}: unknown successors {sorted(unknown)}"
            )
        if gate in values:
            raise InvalidationError(
                f"successorInvalidation.{gate}: self successor is forbidden"
            )
        result[gate] = values
    # DFS cycle check.
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise InvalidationError("successorInvalidation contains a cycle")
        if node in visited:
            return
        visiting.add(node)
        for successor in result[node]:
            visit(successor)
        visiting.remove(node)
        visited.add(node)

    for gate in gate_ids:
        visit(gate)
    return result


def load_graph(path: Path, gate_ids: tuple[str, ...] | list[str]) -> dict[str, tuple[str, ...]]:
    contract = load_contract(path)
    raw = contract.get("successorInvalidation")
    if raw is None:
        # A missing graph is safe but unoptimised: every gate invalidates all
        # later gates in profile order.
        ordered = tuple(gate_ids)
        raw = {
            gate: list(ordered[index + 1 :])
            for index, gate in enumerate(ordered)
        }
    if not isinstance(raw, dict):
        raise InvalidationError("successorInvalidation must be a mapping")
    return validate_graph(raw, gate_ids)


def downstream_closure(
    graph: Mapping[str, tuple[str, ...]], roots: set[str]
) -> set[str]:
    result = set(roots)
    stack = list(roots)
    while stack:
        gate = stack.pop()
        for successor in graph.get(gate, ()):
            if successor not in result:
                result.add(successor)
                stack.append(successor)
    return result


def impacted_gates(
    policies: Mapping[str, InvalidationPolicy],
    changes: list[ChangedInput] | tuple[ChangedInput, ...],
) -> set[str]:
    roots: set[str] = set()
    known_types = set().union(*(policy.input_types for policy in policies.values()))
    for change in changes:
        # An unclassified change cannot prove non-impact, so invalidate the full
        # profile and let successor closure preserve ordered reruns.
        if change.type not in known_types or change.classes is None:
            roots.update(policies)
            continue
        for gate, policy in policies.items():
            if change.type not in policy.input_types:
                continue
            if policy.classes is None or not change.classes or change.classes & policy.classes:
                roots.add(gate)
    return roots


def invalidation_plan(
    *,
    policies: Mapping[str, InvalidationPolicy],
    graph: Mapping[str, tuple[str, ...]],
    changes: list[ChangedInput] | tuple[ChangedInput, ...],
    gate_order: tuple[str, ...] | list[str],
) -> tuple[str, ...]:
    roots = impacted_gates(policies, changes)
    affected = downstream_closure(graph, roots)
    return tuple(gate for gate in gate_order if gate in affected)


def policy_map_from_contract(
    contract_path: Path, gate_ids: tuple[str, ...] | list[str]
) -> dict[str, InvalidationPolicy]:
    contract = load_contract(contract_path)
    raw = contract.get("gatePolicies")
    if not isinstance(raw, dict):
        raise InvalidationError("gatePolicies must be a mapping")
    policies: dict[str, InvalidationPolicy] = {}
    for gate in gate_ids:
        value = raw.get(gate)
        if not isinstance(value, dict):
            raise InvalidationError(f"missing gate policy {gate}")
        inputs = value.get("invalidationInputs")
        if not isinstance(inputs, list) or not inputs:
            raise InvalidationError(f"{gate}.invalidationInputs must be a non-empty list")
        classes_raw = value.get("invalidationClasses")
        classes = None
        if classes_raw is not None:
            if not isinstance(classes_raw, list) or not classes_raw:
                raise InvalidationError(f"{gate}.invalidationClasses must be a non-empty list")
            classes = frozenset(classes_raw)
        policies[gate] = InvalidationPolicy(
            gate=gate,
            input_types=frozenset(inputs),
            classes=classes,
        )
    return policies

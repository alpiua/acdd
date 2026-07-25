#!/usr/bin/env python3
"""Generate or refresh the ``## ACDD contract fingerprint`` block of a bound task.

Every field of that block is derived from the document's own semantic sections by
``acdd_fingerprint.semantic_task_fingerprint``. Transcribing the digests and the
identifier list by hand is pure copying and the usual source of a stale
``sha256``/``ids`` pair, so this script prints or writes the canonical block.

  python3 scripts/record_fingerprint.py --document task.md
  python3 scripts/record_fingerprint.py --document task.md --write

``--red-evidence-id`` is repeatable and preserved across refreshes when omitted:
the existing ``redEvidenceIds`` list is reused, because it names authored red
evidence rather than derived state.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from acdd_fingerprint import (
    FingerprintError,
    markdown_sections,
    semantic_task_fingerprint,
    yaml_documents,
)

HEADING = "## ACDD contract fingerprint"
SECTION_RE = re.compile(
    r"(?m)^## ACDD contract fingerprint[ \t]*\n(?P<body>.*?)(?=^## |\Z)",
    re.DOTALL,
)


def _existing_red_evidence_ids(text: str) -> tuple[str, ...]:
    sections = markdown_sections(text)
    body = sections.get("ACDD contract fingerprint")
    if body is None:
        return ()
    try:
        documents = yaml_documents(body, HEADING)
    except FingerprintError:
        return ()
    if len(documents) != 1 or not isinstance(documents[0], dict):
        return ()
    raw = documents[0].get("redEvidenceIds")
    if not isinstance(raw, list):
        return ()
    return tuple(str(item) for item in raw)


def _render(text: str, red_evidence_ids: tuple[str, ...]) -> str:
    fingerprint = semantic_task_fingerprint(text)
    ids = ", ".join(fingerprint.ids)
    red_ids = ", ".join(red_evidence_ids)
    return (
        "```yaml\n"
        "apiVersion: acdd/semantic-fingerprint/v1\n"
        "kind: semantic-fingerprint\n"
        f"sha256: {fingerprint.sha256}\n"
        f"ids: [{ids}]\n"
        f"redProofFingerprint: {fingerprint.red_proof_sha256}\n"
        f"redEvidenceIds: [{red_ids}]\n"
        "```\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", required=True, type=Path)
    parser.add_argument(
        "--red-evidence-id",
        action="append",
        dest="red_evidence_ids",
        default=None,
        help="authored red evidence id; repeat. Existing ids are reused when omitted.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="replace the section in place instead of printing it",
    )
    args = parser.parse_args()

    text = args.document.read_text(encoding="utf-8")
    red_evidence_ids = (
        tuple(args.red_evidence_ids)
        if args.red_evidence_ids is not None
        else _existing_red_evidence_ids(text)
    )
    try:
        block = _render(text, red_evidence_ids)
    except FingerprintError as exc:
        print(f"record_fingerprint: {exc}", file=sys.stderr)
        return 1

    if not args.write:
        print(f"{HEADING}\n\n{block}", end="")
        return 0

    match = SECTION_RE.search(text)
    if match is None:
        print(
            f"record_fingerprint: {args.document}: missing {HEADING!r} section",
            file=sys.stderr,
        )
        return 1
    # The rendered block is derived from the semantic sections, which exclude this
    # section, so replacing it cannot change its own inputs.
    updated = text[: match.start("body")] + f"\n{block}" + text[match.end("body") :]
    args.document.write_text(updated, encoding="utf-8")
    print(f"record_fingerprint: updated {HEADING} in {args.document}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

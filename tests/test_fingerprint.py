"""Tests for fingerprint computation."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acdd.fingerprint import fingerprint_gate


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "src" / "a.py").write_text("alpha")
    (tmp_path / "src" / "b.py").write_text("beta")
    (tmp_path / "config" / "app.yaml").write_text("k: v")
    return tmp_path


def test_fingerprint_selects_types(ws):
    inputs = [{"type": "source", "path": "src/a.py"},
              {"type": "test", "path": "src/b.py"},
              {"type": "configuration", "path": "config/app.yaml"}]
    fp_src = fingerprint_gate(ws, inputs, types=["source"])
    fp_all = fingerprint_gate(ws, inputs, types=["source", "test", "configuration"])
    assert fp_src.sha256 != fp_all.sha256
    assert fp_src.scope == ("src/a.py",)


def test_fingerprint_filters_by_files(ws):
    inputs = [{"type": "source", "path": "src/a.py"},
              {"type": "source", "path": "src/b.py"}]
    fp_a = fingerprint_gate(ws, inputs, types=["source"], files=["src/a.py"])
    fp_b = fingerprint_gate(ws, inputs, types=["source"], files=["src/b.py"])
    fp_ab = fingerprint_gate(ws, inputs, types=["source"], files=["src/a.py", "src/b.py"])
    assert fp_a.sha256 != fp_b.sha256
    assert fp_a.sha256 != fp_ab.sha256


def test_fingerprint_deterministic(ws):
    inputs = [{"type": "source", "path": "src/a.py"}]
    fp1 = fingerprint_gate(ws, inputs, types=["source"])
    fp2 = fingerprint_gate(ws, inputs, types=["source"])
    assert fp1.sha256 == fp2.sha256


def test_fingerprint_missing_file_marker(ws):
    inputs = [{"type": "source", "path": "src/missing.py"}]
    fp = fingerprint_gate(ws, inputs, types=["source"])
    assert fp.sha256.startswith("sha256:")


def test_directory_entries_have_unambiguous_encoding(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "a").write_bytes(b"bPAYLOAD")
    inputs = [{"type": "source", "path": "src"}]
    first = fingerprint_gate(tmp_path, inputs, types=["source"]).sha256
    (source / "a").rename(source / "ab")
    (source / "ab").write_bytes(b"PAYLOAD")
    assert fingerprint_gate(tmp_path, inputs, types=["source"]).sha256 != first

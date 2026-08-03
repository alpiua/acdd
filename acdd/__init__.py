"""ACDD — Architecture Contract-Driven Development."""
from .adapter import Adapter, AdapterError, index_adapters, load_adapter
from .fingerprint import fingerprint_for_gate, fingerprint_gate
from .model import (
    AcddError,
    Check,
    Document,
    Gate,
    Profile,
    Subtask,
    load_document,
    load_profile,
)
from .record import finalize_gate, record_check, record_review
from .paths import resolve_profile, share_dir, share_path
from .validate import validate

__all__ = ["AcddError", "Adapter", "AdapterError", "Check", "Document", "Gate", "Profile", "Subtask", "finalize_gate", "fingerprint_for_gate", "fingerprint_gate", "index_adapters", "load_adapter", "load_document", "load_profile", "record_check", "record_review", "resolve_profile", "share_dir", "share_path", "validate"]

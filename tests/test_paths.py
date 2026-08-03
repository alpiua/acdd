import pytest

from acdd.paths import resolve_profile, share_dir, share_path


def test_share_dir_contains_profiles_and_skills():
    root = share_dir()
    assert (root / "profiles" / "task" / "v1.yaml").is_file()
    assert (root / "skills" / "design" / "SKILL.md").is_file()


def test_resolve_profile_accepts_alias_and_path():
    aliased = resolve_profile("task")
    assert aliased.name == "v1.yaml"
    assert aliased.is_file()
    assert resolve_profile(aliased) == aliased.resolve()
    assert resolve_profile("acdd/plan/v1").is_file()


def test_resolve_profile_rejects_unknown_alias():
    with pytest.raises(FileNotFoundError):
        resolve_profile("missing-profile")


def test_share_path_reads_adapter_example():
    assert share_path("adapters", "task.yaml").is_file()
    assert share_path("examples", "task-example.md").is_file()

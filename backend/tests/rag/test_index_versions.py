import json

import pytest

from app.rag.index_versions import (
    activate_index,
    new_index_version,
    resolve_active_index,
    restore_active_index,
    version_directory,
)


def test_candidate_activation_and_legacy_restore_are_atomic(tmp_path) -> None:
    index_root = tmp_path / "rag_index"
    version = new_index_version("a" * 64)
    candidate = version_directory(index_root, version)
    candidate.mkdir(parents=True)
    (candidate / "manifest.json").write_text("{}", encoding="utf-8")

    pointer = activate_index(index_root, version)
    active_path, active_version = resolve_active_index(index_root)

    assert pointer["index_version"] == version
    assert active_path == candidate.resolve()
    assert active_version == version
    assert json.loads((index_root / "active.json").read_text(encoding="utf-8"))[
        "index_version"
    ] == version

    restore_active_index(index_root, "legacy")
    assert resolve_active_index(index_root) == (index_root, "legacy")


@pytest.mark.parametrize("unsafe", ["../escape", "one/two", "one\\two", ""])
def test_version_directory_rejects_unsafe_versions(tmp_path, unsafe) -> None:
    with pytest.raises(ValueError):
        version_directory(tmp_path, unsafe)


def test_invalid_active_pointer_is_not_silently_ignored(tmp_path) -> None:
    index_root = tmp_path / "rag_index"
    index_root.mkdir()
    (index_root / "active.json").write_text(
        '{"index_version":"missing"}', encoding="utf-8"
    )

    with pytest.raises(RuntimeError, match="unavailable"):
        resolve_active_index(index_root)

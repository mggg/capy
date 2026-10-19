"""Temporary-file cleanup and replacement preserve completed outputs."""

from pathlib import Path

import pytest
from national_pipeline.stage_files import stage_file


@pytest.mark.parametrize("failure", [OSError("write failed"), KeyboardInterrupt()])
def test_failed_write_discards_partial_file_and_preserves_previous_output(tmp_path, failure):
    destination = tmp_path / "record.json"
    destination.write_bytes(b"previous record")

    with pytest.raises(type(failure)), stage_file(tmp_path) as temporary_path:
        temporary_path.write_bytes(b"partial replacement")
        raise failure

    assert destination.read_bytes() == b"previous record"
    assert not list(tmp_path.glob(".retrieval-*"))


def test_failed_publication_preserves_existing_file(tmp_path, monkeypatch):
    destination = tmp_path / "record.json"
    destination.write_bytes(b"previous record")

    def refuse_replacement(*args):
        raise OSError("Cannot replace destination")

    monkeypatch.setattr(Path, "replace", refuse_replacement)
    with pytest.raises(OSError, match="Cannot replace"), stage_file(tmp_path) as temporary_path:
        temporary_path.write_bytes(b"replacement bytes")
        temporary_path.replace(destination)

    assert destination.read_bytes() == b"previous record"
    assert not list(tmp_path.glob(".retrieval-*"))


def test_file_replacement_preserves_other_hard_links(tmp_path):
    destination = tmp_path / "record.json"
    destination.write_bytes(b"previous record")
    (tmp_path / "old_record.json").hardlink_to(destination)

    with stage_file(tmp_path) as temporary_path:
        temporary_path.write_bytes(b"replacement bytes")
        temporary_path.replace(destination)

    assert destination.read_bytes() == b"replacement bytes"
    assert (tmp_path / "old_record.json").read_bytes() == b"previous record"
    assert not list(tmp_path.glob(".retrieval-*"))

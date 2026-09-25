"""Storage ownership across writes, publication, and failures."""

from pathlib import Path

import pytest
from capy_core.stage_files import stage_file


def test_failed_stream_cannot_be_published_or_retried(tmp_path):
    def failed_chunks():
        yield b"first"
        raise OSError("read failed")

    with stage_file(tmp_path) as staged:
        with pytest.raises(OSError, match="read failed"):
            staged.write_chunks(failed_chunks())

        with pytest.raises(ValueError, match="completed staged file"):
            staged.publish(tmp_path / "published")

        with pytest.raises(ValueError, match="only once"):
            staged.write_chunks((b"replacement",))

    assert not list(tmp_path.iterdir())


def test_interrupted_stream_discards_written_bytes(tmp_path):
    def interrupted_chunks():
        yield b"first"
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt), stage_file(tmp_path) as staged:
        staged.write_chunks(interrupted_chunks())

    assert not list(tmp_path.iterdir())


def test_failed_publication_preserves_existing_file(tmp_path, monkeypatch):
    destination = tmp_path / "record.json"
    destination.write_bytes(b"previous record")

    def refuse_replacement(*args):
        raise OSError("Cannot replace destination")

    monkeypatch.setattr(Path, "replace", refuse_replacement)
    with pytest.raises(OSError, match="Cannot replace"), stage_file(tmp_path) as staged:
        staged.write_chunks((b"replacement bytes",))
        staged.publish(destination)

    assert destination.read_bytes() == b"previous record"
    assert not list(tmp_path.glob(".retrieval-*"))


def test_file_replacement_preserves_other_hard_links(tmp_path):
    destination = tmp_path / "record.json"
    destination.write_bytes(b"previous record")
    (tmp_path / "old_record.json").hardlink_to(destination)

    with stage_file(tmp_path) as staged:
        staged.write_chunks((b"replacement bytes",))
        staged.publish(destination)

    assert destination.read_bytes() == b"replacement bytes"
    assert (tmp_path / "old_record.json").read_bytes() == b"previous record"

    assert not list(tmp_path.glob(".retrieval-*"))

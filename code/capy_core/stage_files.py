"""Prepare files under temporary names, then move completed files to their final names."""

import os
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@contextmanager
def stage_file(directory: Path) -> Iterator["StagedFile"]:
    """Create a temporary file and remove it when the ``with`` block ends unless it was saved.

    Staging means filling and checking a file under a temporary name before giving it its final
    filename. Call publish() inside the block to keep the completed file. If the block ends
    without publication, including after an error, the temporary file is removed.

    Args:
        directory (Path): Directory for the temporary file, created if absent. It must be on the
            same filesystem as the final file so publication can use a single rename.

    Yields:
        StagedFile: Empty file that can be filled once and then moved to its final filename.
            Published files remain there after the block ends.

    Raises:
        OSError: Creating or cleaning up the temporary file fails.
    """
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".retrieval-", dir=directory)
    os.close(descriptor)

    staged = StagedFile(Path(temporary_name))
    try:
        yield staged
    finally:
        staged._close()


@dataclass
class StagedFile:
    """Keep track of a temporary file until it is removed or moved to its final filename.

    Create this object through stage_file(), which handles cleanup. Use write_chunks() to write
    bytes. The path is available for reading and checking those bytes, not for writing them
    directly. After a failed write, start a new staging block instead of reusing this file.
    """

    path: Path
    _state: Literal["empty", "writing", "ready", "published", "closed"] = field(
        default="empty", init=False
    )

    def write_chunks(self, chunks: Iterable[bytes]) -> None:
        """Fill the temporary file once, writing each supplied piece of data in order.

        If producing or writing a piece fails, the partial file cannot be published or written
        again. The surrounding stage_file() block removes it when that block ends.

        Args:
            chunks (Iterable[bytes]): Pieces of file data, produced one at a time.

        Raises:
            ValueError: The file has already been used.
            OSError: Writing the file fails.

        Errors raised while producing chunks also pass back to the caller.
        """
        self._require_empty()
        self._state = "writing"
        with self.path.open("wb") as stream:
            for chunk in chunks:
                stream.write(chunk)

        self._state = "ready"

    def publish(self, destination: Path) -> None:
        """Move the completed file to its final name, replacing any file already there.

        The rename happens as one filesystem operation, so a reader of the final path sees either
        the previous file or the completed replacement. The caller must check the file before
        calling this method; publication itself does not inspect its contents.

        Args:
            destination (Path): Final filename, in an existing directory on the same filesystem as
                the temporary file.

        Raises:
            ValueError: The staged file has not been filled successfully or is already closed or
                published.
            OSError: Replacing the destination fails.
        """
        if self._state != "ready":
            raise ValueError("Only a completed staged file can be published")

        self.path.replace(destination)
        self._state = "published"

    def _require_empty(self) -> None:
        if self._state != "empty":
            raise ValueError("A staged file can be written only once")

    def _close(self) -> None:
        """Remove the temporary filename, leaving any published file at its final location."""
        self.path.unlink(missing_ok=True)

        self._state = "closed"

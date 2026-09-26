"""Prepare files under temporary names, then move completed files to their final names."""

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def stage_file(directory: Path) -> Iterator[Path]:
    """Create a temporary path and remove it when the ``with`` block ends unless it was moved.

    Write to the path with ordinary file operations or a library such as pandas. After writing
    and checking the file, call temporary_path.replace(destination) inside the block to keep it.
    Close any open file handles before replacing it. If writing or checking fails, let the error
    leave the block so cleanup removes the partial file. Leaving the block never publishes a file
    automatically, including when a download is still pending.

    Args:
        directory (Path): Directory for the temporary file, created if absent. Use the final
            file's directory so replacement is a single operation on the same filesystem.

    Yields:
        Path: Empty temporary file, owned by this context. A completed file moved to its final
            name remains there after the block ends.

    Raises:
        OSError: Creating or cleaning up the temporary file fails.
    """
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".retrieval-", dir=directory)
    os.close(descriptor)

    temporary_path = Path(temporary_name)
    try:
        yield temporary_path
    finally:
        temporary_path.unlink(missing_ok=True)

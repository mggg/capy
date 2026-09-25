"""Record raw-file checksums for diagnosing differences in replication results."""

import argparse
import hashlib
from pathlib import Path

from capy_core.pipeline_config import load_configuration
from capy_core.retrieve_data.prepare_file_requests import (
    build_raw_file_requests,
    select_raw_file_requests,
)
from capy_core.retrieve_data.raw_file_requests import RawFileRequest
from capy_core.stage_files import stage_file


def record_raw_checksums(
    raw_data_directory: Path,
    requests: list[RawFileRequest],
    output_path: Path,
) -> None:
    """Write SHA-256 digests and relative filenames in definition order.

    Args:
        raw_data_directory (Path): Directory containing the completed raw inputs.
        requests (list[RawFileRequest]): Files selected from the versioned Python definitions.
        output_path (Path): Checksum list to create or replace, outside the raw-data directory.

    Raises:
        ValueError: The output is inside raw_data_directory, where it could overwrite an input.
        OSError: An input is missing/unreadable or the output cannot be written.

    This publication operation is separate from retrieval. It records the bytes present without
    comparing or rejecting them. The output uses sha256sum's digest, two spaces, filename format.
    A failed read leaves any previous checksum list intact.
    """
    if output_path.resolve().is_relative_to(raw_data_directory.resolve()):
        raise ValueError("Save the checksum list outside the raw-data directory")

    lines = []
    for request in requests:
        relative_path = request.destination_relative_path
        with (raw_data_directory / relative_path).open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()

        lines.append(f"{checksum}  {relative_path}\n")

    with stage_file(output_path.parent) as staged:
        staged.write_chunks(("".join(lines).encode("utf-8"),))
        staged.publish(output_path)


def main() -> None:
    """Build the selected raw-file requests and write its checksum reference for publication."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Override the configured checksum output")
    args = parser.parse_args()

    repository = Path(__file__).resolve().parents[1]
    config = load_configuration(args.config)
    available_requests = build_raw_file_requests(config)
    selected_requests = select_raw_file_requests(available_requests, config.file_path_patterns)
    output_path = args.output if args.output is not None else repository / config.raw_checksums_file
    record_raw_checksums(repository / config.raw_data_directory, selected_requests, output_path)
    print(f"Recorded checksums for {len(selected_requests)} raw files in {output_path}")


if __name__ == "__main__":
    main()

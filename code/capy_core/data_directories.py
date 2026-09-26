"""Resolve a stage's output directory and keep it separate from that stage's inputs."""

from pathlib import Path


def resolve_separate_output_directory(
    repository_root: Path,
    configured_output_directory: Path,
    input_directories: tuple[Path, ...],
) -> Path:
    """Resolve an output folder and reject overlap with any supplied input folder.

    Equal folders and nesting in either direction are rejected, including through symlinks.
    Only the current stage's inputs are checked. No folders are created or files removed.

    Args:
        repository_root (Path): Base for relative configured output paths.
        configured_output_directory (Path): Output setting; absolute paths retain their location.
        input_directories (tuple[Path, ...]): Absolute input roots used by this stage.

    Returns:
        Path: Resolved absolute output directory, separate from every supplied input root.

    Raises:
        OSError: A path cannot be resolved.
        ValueError: The output directory equals, contains, or lies within an input directory.
    """
    output_directory = (repository_root / configured_output_directory).resolve()

    for input_directory in input_directories:
        input_directory = input_directory.resolve()

        if output_directory.is_relative_to(input_directory) or input_directory.is_relative_to(
            output_directory
        ):
            raise ValueError(
                "Output and input directories must be separate, without nesting: "
                f"{output_directory} and {input_directory}"
            )

    return output_directory

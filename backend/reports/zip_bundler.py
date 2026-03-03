from __future__ import annotations

"""Zip bundler — packages multiple files into a .zip archive."""

import logging
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


class ZipBundler:
    """Create a zip archive from a list of source files."""

    def create_zip(self, files: list[tuple[Path, str]], output_path: Path) -> Path:
        """Package files into a zip archive.

        Args:
            files: List of ``(source_path, archive_name)`` tuples.
                ``source_path`` is the file on disk; ``archive_name`` is the
                path inside the zip (e.g. ``"markdown/00-cover.md"``).
            output_path: Destination path for the .zip file.

        Returns:
            The ``output_path`` after writing.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for source, arcname in files:
                if source.is_file():
                    zf.write(source, arcname)
                elif source.is_dir():
                    for child in sorted(source.rglob("*")):
                        if child.is_file():
                            zf.write(child, f"{arcname}/{child.relative_to(source)}")

        logger.info("Zip bundle created: %s (%d entries)", output_path, len(files))
        return output_path

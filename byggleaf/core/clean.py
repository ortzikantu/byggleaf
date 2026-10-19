"""Safe removal of the generated output directory.

``clean`` is intentionally narrower than a general-purpose ``rm -rf``: it only
touches ``public/``.  Symlinks are unlinked rather than followed, so a user can
never accidentally clean a directory outside the project.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


class CleanError(RuntimeError):
    """The generated output directory could not be removed."""


@dataclass(frozen=True, slots=True)
class CleanResult:
    """What the clean command found and what it did."""

    output_dir: Path
    removed: bool
    kind: str


def clean_output(root: Path) -> CleanResult:
    """Delete ``<root>/public`` and return a factual result.

    Missing output is successful and idempotent.  A symlink named ``public`` is
    unlinked, never traversed.  A regular directory is removed recursively.
    """

    root = Path(root).resolve()
    output = root / "public"

    if not output.exists() and not output.is_symlink():
        return CleanResult(output_dir=output, removed=False, kind="missing")

    try:
        if output.is_symlink():
            output.unlink()
            kind = "symlink"
        elif output.is_dir():
            if os.path.ismount(output):
                raise CleanError(
                    f"{output} is a mount point; refusing to remove it"
                )
            shutil.rmtree(output)
            kind = "directory"
        else:
            # Handles regular files and unusual entries without ever following
            # a link (the symlink branch above already caught those).
            output.unlink()
            kind = "file"
    except OSError as exc:
        raise CleanError(f"cannot remove {output}: {exc}") from exc

    return CleanResult(output_dir=output, removed=True, kind=kind)

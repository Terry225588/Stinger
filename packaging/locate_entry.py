"""PyInstaller entry path. The spec file lives in packaging/, main.py is the repo root."""

from __future__ import annotations

from pathlib import Path


def resolve_entry(spec_location: Path | str) -> Path:
    location = Path(spec_location).resolve()
    spec_dir = location.parent if location.is_file() else location
    entry = spec_dir.parent / "main.py"
    if not entry.is_file():
        raise FileNotFoundError(f"entry script not found: {entry}")
    return entry

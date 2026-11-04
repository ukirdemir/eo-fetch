"""Helpers for the ``eo-fetch login`` commands: hidden prompts and private credential files."""

from __future__ import annotations

import contextlib
import getpass
from pathlib import Path


def ask_secret(prompt: str) -> str:
    """Ask for a secret without echoing it; an empty answer is an error."""
    value = getpass.getpass(prompt).strip()
    if not value:
        raise ValueError("Nothing entered")
    return value


def confirm_overwrite(path: Path) -> bool:
    """True when the file does not exist, or the user agrees to replace it."""
    if not path.exists():
        return True
    answer = input(f"{path} exists. Replace it? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def write_private(path: Path, text: str) -> None:
    """Write a credentials file (plain text) readable only by the user where the OS allows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    with contextlib.suppress(OSError):  # Windows ignores POSIX modes
        path.chmod(0o600)

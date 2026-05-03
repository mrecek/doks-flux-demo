"""Subprocess helpers: streaming and capturing."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence


def stream(
    cmd: Sequence[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    input_text: str | None = None,
) -> int:
    """Run a command with output going straight to the terminal. Returns exit code."""
    return subprocess.run(
        list(cmd),
        env=env,
        cwd=cwd,
        check=False,
        input=input_text,
        text=True if input_text is not None else None,
    ).returncode


def capture(
    cmd: Sequence[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> tuple[int, str, str]:
    """Run a command and capture stdout/stderr. Returns (returncode, stdout, stderr)."""
    result = subprocess.run(
        list(cmd),
        env=env,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr

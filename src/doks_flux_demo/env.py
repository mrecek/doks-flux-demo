"""Load and validate .env."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

from dotenv import dotenv_values
from rich.console import Console

from .paths import PROJECT_ROOT

_out = Console()
_REQUIRED = ("DIGITALOCEAN_TOKEN", "TS_OPERATOR_CLIENT_ID", "TS_OPERATOR_CLIENT_SECRET")
_REQUIRED_TOOLS = ("doctl", "flux", "gh", "git", "kubectl", "terragrunt", "tofu")


@dataclass(frozen=True)
class Env:
    do_token: str
    ts_client_id: str
    ts_client_secret: str
    github_token: str

    def child_env(self) -> dict[str, str]:
        """Environment passed to subprocesses (terragrunt, doctl, flux, ...)."""
        return {
            **os.environ,
            "DIGITALOCEAN_TOKEN": self.do_token,
            "DIGITALOCEAN_ACCESS_TOKEN": self.do_token,
            "TF_VAR_digitalocean_token": self.do_token,
            "GITHUB_TOKEN": self.github_token,
        }


def load_env() -> Env:
    """Read .env, fall back to process env for missing keys, validate required keys."""
    dotenv_path = PROJECT_ROOT / ".env"
    file_values = dotenv_values(dotenv_path) if dotenv_path.exists() else {}

    def _get(key: str) -> str:
        value = (file_values.get(key) or os.environ.get(key) or "").strip()
        return value

    missing = [key for key in _REQUIRED if not _get(key)]
    if missing:
        _out.print("[red]Missing required values in .env:[/red]")
        for key in missing:
            _out.print(f"  - {key}")
        _out.print("\nCopy [bold].env.example[/bold] to [bold].env[/bold] and fill in the values.")
        raise SystemExit(2)

    return Env(
        do_token=_get("DIGITALOCEAN_TOKEN"),
        ts_client_id=_get("TS_OPERATOR_CLIENT_ID"),
        ts_client_secret=_get("TS_OPERATOR_CLIENT_SECRET"),
        github_token=_get_github_token(),
    )


def _get_github_token() -> str:
    """Pull the GitHub token from `gh auth token`. Required for `flux bootstrap`."""
    if not shutil.which("gh"):
        _out.print("[red]GitHub CLI (`gh`) is not installed.[/red]")
        _out.print("Install it: https://cli.github.com/")
        raise SystemExit(2)
    result = subprocess.run(
        ["gh", "auth", "token"], capture_output=True, text=True, check=False
    )
    token = result.stdout.strip()
    if result.returncode != 0 or not token:
        _out.print("[red]GitHub CLI is not authenticated.[/red]")
        _out.print("Run [bold]gh auth login[/bold] and try again.")
        raise SystemExit(2)
    return token


def ensure_tools() -> None:
    """Verify all required CLI tools are on PATH."""
    missing = [tool for tool in _REQUIRED_TOOLS if not shutil.which(tool)]
    if missing:
        _out.print("[red]Required tools not found on PATH:[/red]")
        for tool in missing:
            _out.print(f"  - {tool}")
        _out.print("\nInstall missing tools and re-run.")
        raise SystemExit(2)


def get_origin_repo() -> tuple[str, str]:
    """Parse `git remote get-url origin` into (owner, repo)."""
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _out.print("[red]Failed to read git origin remote.[/red]")
        _out.print("Ensure this checkout has an `origin` remote configured (your fork).")
        raise SystemExit(2)
    url = result.stdout.strip()
    # Match HTTPS, SSH, or ssh:// forms.
    for prefix, sep in (("https://github.com/", "/"), ("git@github.com:", "/"), ("ssh://git@github.com/", "/")):
        if url.startswith(prefix):
            rest = url[len(prefix) :]
            if rest.endswith(".git"):
                rest = rest[:-4]
            owner, _, repo = rest.partition(sep)
            if owner and repo:
                return owner, repo
    _out.print(f"[red]Unsupported origin remote URL: {url}[/red]")
    _out.print("Expected a github.com origin remote (HTTPS or SSH).")
    raise SystemExit(2)

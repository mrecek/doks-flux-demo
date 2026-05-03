"""Read non-secret cluster identity from terragrunt.hcl (single source of truth)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rich.console import Console

from .paths import TOFU_DEPLOYMENT

_out = Console()
_TERRAGRUNT_HCL = TOFU_DEPLOYMENT / "terragrunt.hcl"
_STRING_ASSIGN = re.compile(r'^\s*(\w+)\s*=\s*"([^"]+)"', re.MULTILINE)


@dataclass(frozen=True)
class Config:
    cluster_name: str
    project_name: str


def load_config() -> Config:
    if not _TERRAGRUNT_HCL.exists():
        _out.print(f"[red]Missing {_TERRAGRUNT_HCL}.[/red]")
        raise SystemExit(2)
    pairs = dict(_STRING_ASSIGN.findall(_TERRAGRUNT_HCL.read_text()))
    missing = [key for key in ("cluster_name", "project_name") if key not in pairs]
    if missing:
        _out.print(
            f"[red]Could not find {', '.join(missing)} in {_TERRAGRUNT_HCL}.[/red]"
        )
        raise SystemExit(2)
    return Config(cluster_name=pairs["cluster_name"], project_name=pairs["project_name"])

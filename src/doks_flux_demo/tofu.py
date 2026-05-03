"""Terragrunt plan/apply/destroy plus plan parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rich.console import Console
from rich.table import Table

from .paths import TOFU_DEPLOYMENT
from .runner import capture, stream

_out = Console()

_RESOURCE_ACTION_RE = re.compile(
    r"^\s*#\s+(\S+)\s+will be\s+(created|updated|destroyed|replaced|read)"
)
_PLAN_SUMMARY_RE = re.compile(
    r"Plan:\s+(\d+)\s+to add,\s+(\d+)\s+to change,\s+(\d+)\s+to destroy"
)
_ATTRIBUTE_RE = re.compile(r'^\s+[+~-]\s+(\w+)\s+=\s+"?([^"]*)"?\s*$')
_NO_CHANGES_RE = re.compile(r"No changes\.")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_TG_PREFIX_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d+\s+\w+\s+tofu:\s?")

_DISPLAY_ATTRIBUTES = frozenset(
    {"name", "region", "version", "ha", "auto_upgrade", "surge_upgrade"}
)
_NODE_POOL_ATTRIBUTES = frozenset({"node_count", "size"})

_FRIENDLY_LABELS = {
    "name": "Cluster",
    "region": "Region",
    "version": "K8s Version",
    "ha": "HA Control Plane",
    "auto_upgrade": "Auto-upgrade",
    "surge_upgrade": "Surge Upgrade",
    "node_count": "Node Count",
    "size": "Node Size",
}

_ACTION_STYLES = {
    "created": "[green]create[/green]",
    "updated": "[yellow]update[/yellow]",
    "destroyed": "[red]destroy[/red]",
    "replaced": "[red]replace[/red]",
    "read": "[dim]read[/dim]",
}


@dataclass
class PlanSummary:
    to_add: int = 0
    to_change: int = 0
    to_destroy: int = 0
    no_changes: bool = False
    resource_actions: list[tuple[str, str]] = field(default_factory=list)
    cluster_values: dict[str, str] = field(default_factory=dict)
    node_pool_values: dict[str, str] = field(default_factory=dict)


def parse_plan(output: str) -> PlanSummary:
    plan = PlanSummary()
    in_cluster_block = False
    in_node_pool_block = False

    for raw in output.splitlines():
        line = _ANSI_RE.sub("", raw)
        line = _TG_PREFIX_RE.sub("", line)

        m = _RESOURCE_ACTION_RE.match(line)
        if m:
            addr = m.group(1)
            plan.resource_actions.append((addr, m.group(2)))
            in_cluster_block = "kubernetes_cluster" in addr
            in_node_pool_block = False
            continue

        if in_cluster_block and re.match(r"^\s+[+~]\s+node_pool\s*\{", line):
            in_node_pool_block = True
            continue

        m = _PLAN_SUMMARY_RE.search(line)
        if m:
            plan.to_add = int(m.group(1))
            plan.to_change = int(m.group(2))
            plan.to_destroy = int(m.group(3))
            continue

        m = _ATTRIBUTE_RE.match(line)
        if m:
            key, value = m.group(1), m.group(2)
            if in_node_pool_block and key in _NODE_POOL_ATTRIBUTES:
                plan.node_pool_values[key] = value
            elif in_cluster_block and not in_node_pool_block and key in _DISPLAY_ATTRIBUTES:
                plan.cluster_values[key] = value
            continue

        if in_node_pool_block and re.match(r"^\s+\}", line):
            in_node_pool_block = False

        if _NO_CHANGES_RE.search(line):
            plan.no_changes = True

    return plan


def _friendly(value: str) -> str:
    if value in ("true", "True"):
        return "Yes"
    if value in ("false", "False"):
        return "No"
    if value in ("", "(known after apply)"):
        return "(auto)"
    return value


def display_plan(plan: PlanSummary) -> None:
    combined = {**plan.cluster_values, **plan.node_pool_values}
    if combined:
        config_table = Table(title="Cluster Configuration")
        config_table.add_column("Setting", style="bold")
        config_table.add_column("Value")
        for key in (
            "name", "region", "version", "size", "node_count",
            "ha", "auto_upgrade", "surge_upgrade",
        ):
            if key in combined:
                config_table.add_row(_FRIENDLY_LABELS.get(key, key), _friendly(combined[key]))
        _out.print(config_table)
        _out.print()

    if plan.resource_actions:
        changes_table = Table(title="Resource Changes")
        changes_table.add_column("Resource", style="bold")
        changes_table.add_column("Action")
        for resource, action in plan.resource_actions:
            changes_table.add_row(resource, _ACTION_STYLES.get(action, action))
        _out.print(changes_table)
        _out.print()

    _out.print(
        f"[bold]Plan:[/bold] "
        f"[green]{plan.to_add} to add[/green], "
        f"[yellow]{plan.to_change} to change[/yellow], "
        f"[red]{plan.to_destroy} to destroy[/red]"
    )


def run_plan(env: dict[str, str]) -> str:
    """Run terragrunt plan, capture and return the text. Exits on failure."""
    code, stdout, stderr = capture(["terragrunt", "plan"], env=env, cwd=TOFU_DEPLOYMENT)
    if code != 0:
        _out.print(stdout)
        _out.print(stderr)
        _out.print("[red]terragrunt plan failed.[/red]")
        raise SystemExit(1)
    return stdout


def run_apply(env: dict[str, str]) -> None:
    code = stream(["terragrunt", "apply", "-auto-approve"], env=env, cwd=TOFU_DEPLOYMENT)
    if code != 0:
        _out.print("[red]terragrunt apply failed.[/red]")
        raise SystemExit(1)


def run_destroy(env: dict[str, str]) -> None:
    code = stream(["terragrunt", "destroy", "-auto-approve"], env=env, cwd=TOFU_DEPLOYMENT)
    if code != 0:
        _out.print("[red]terragrunt destroy failed.[/red]")
        raise SystemExit(1)

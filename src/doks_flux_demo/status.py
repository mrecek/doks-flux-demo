"""Render a health snapshot of cluster, Flux, and workloads."""

from __future__ import annotations

import json

from rich.console import Console
from rich.table import Table

from .doctl import get_cluster_info
from .runner import capture

_out = Console()
_FLUX_KUSTOMIZATIONS = ("flux-system", "infra-edge", "apps-uptime-kuma")


def _kubectl_json(args: list[str], env: dict[str, str]) -> dict | None:
    code, stdout, _ = capture(["kubectl", *args, "-o", "json"], env=env)
    if code != 0 or not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def _ready(resource: dict | None) -> tuple[bool, str]:
    if not resource:
        return False, "not found"
    for cond in resource.get("status", {}).get("conditions", []):
        if cond.get("type") == "Ready":
            return cond.get("status") == "True", cond.get("message", "") or cond.get("reason", "")
    return False, "no Ready condition"


def _ok(ready: bool) -> str:
    return "[green]OK[/green]" if ready else "[red]FAIL[/red]"


def show_status(cluster_name: str, env: dict[str, str]) -> None:
    table = Table(title="doks-flux-demo status")
    table.add_column("Component", style="bold")
    table.add_column("State")
    table.add_column("Detail")

    info = get_cluster_info(cluster_name, env)
    if info:
        table.add_row(
            "DOKS cluster", _ok(info.status == "running"),
            f"{info.name} / {info.region} / {info.status}",
        )
    else:
        table.add_row("DOKS cluster", "[red]MISSING[/red]", "not found via doctl")
        _out.print(table)
        return

    for name in _FLUX_KUSTOMIZATIONS:
        resource = _kubectl_json(
            ["-n", "flux-system", "get",
             f"kustomization.kustomize.toolkit.fluxcd.io/{name}"],
            env,
        )
        ready, msg = _ready(resource)
        table.add_row(f"Flux: {name}", _ok(ready), msg or "Ready")

    hr = _kubectl_json(
        ["-n", "tailscale", "get", "helmrelease.helm.toolkit.fluxcd.io/tailscale-operator"],
        env,
    )
    ready, msg = _ready(hr)
    table.add_row("Tailscale operator", _ok(ready), msg or "Ready")

    sts = _kubectl_json(
        ["-n", "uptime-kuma-cloud", "get", "statefulset/uptime-kuma-cloud"], env
    )
    if sts:
        spec_replicas = sts.get("spec", {}).get("replicas", 1)
        ready_replicas = sts.get("status", {}).get("readyReplicas", 0)
        is_ready = ready_replicas >= spec_replicas
        table.add_row(
            "uptime-kuma StatefulSet",
            _ok(is_ready),
            f"{ready_replicas}/{spec_replicas} replicas ready",
        )
    else:
        table.add_row("uptime-kuma StatefulSet", "[red]FAIL[/red]", "not found")

    ingress = _kubectl_json(
        ["-n", "uptime-kuma-cloud", "get", "ingress/uptime-kuma-cloud-tailscale"], env
    )
    if ingress:
        rules = ingress.get("status", {}).get("loadBalancer", {}).get("ingress", [])
        host = rules[0].get("hostname", "") if rules else ""
        table.add_row(
            "Tailscale ingress",
            _ok(bool(host)),
            host or "no hostname assigned yet",
        )
    else:
        table.add_row("Tailscale ingress", "[red]FAIL[/red]", "not found")

    _out.print(table)

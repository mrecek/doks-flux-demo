"""DigitalOcean resource audit and cleanup via doctl."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from rich.console import Console

from .runner import capture

_out = Console()


@dataclass(frozen=True)
class DoksClusterInfo:
    uuid: str
    name: str
    region: str
    status: str


@dataclass(frozen=True)
class OrphanedResource:
    kind: str  # "load_balancer", "volume", "firewall"
    id: str
    name: str


@dataclass
class AuditResult:
    cluster_exists: bool = False
    orphans: list[OrphanedResource] = field(default_factory=list)
    project_id: str | None = None
    project_name: str | None = None


def _doctl_json(args: list[str], env: dict[str, str]) -> list[dict]:
    code, stdout, stderr = capture(["doctl", *args, "--output", "json"], env=env)
    if code != 0:
        detail = (stderr or stdout).strip().lower()
        if "not found" in detail or "404" in detail or "no cluster goes by the name" in detail:
            return []
        _out.print(f"[red]doctl {' '.join(args)} failed:[/red] {stderr.strip() or stdout.strip()}")
        raise SystemExit(1)
    if not stdout.strip():
        return []
    parsed = json.loads(stdout)
    if isinstance(parsed, list):
        return parsed
    return [parsed] if parsed else []


def get_cluster_info(name: str, env: dict[str, str]) -> DoksClusterInfo | None:
    items = _doctl_json(["kubernetes", "cluster", "get", name], env)
    if not items:
        return None
    c = items[0]
    return DoksClusterInfo(
        uuid=c["id"],
        name=c["name"],
        region=c.get("region", ""),
        status=c.get("status", {}).get("state", "unknown"),
    )


def get_cluster_status(name: str, env: dict[str, str]) -> str | None:
    info = get_cluster_info(name, env)
    return info.status if info else None


def audit_orphans(
    cluster_uuid: str | None,
    project_name: str,
    env: dict[str, str],
) -> AuditResult:
    """Scan for DO resources that survived a cluster destroy (LB, volume, firewall)."""
    result = AuditResult()
    tag = f"k8s:{cluster_uuid}" if cluster_uuid else None

    if cluster_uuid:
        clusters = _doctl_json(["kubernetes", "cluster", "list"], env)
        if any(c.get("id") == cluster_uuid for c in clusters):
            result.cluster_exists = True
            return result

    if tag:
        for kind, args in (
            ("load_balancer", ["compute", "load-balancer", "list"]),
            ("volume", ["compute", "volume", "list"]),
            ("firewall", ["compute", "firewall", "list"]),
        ):
            for r in _doctl_json(args, env):
                if tag in r.get("tags", []):
                    result.orphans.append(
                        OrphanedResource(kind=kind, id=str(r["id"]), name=r.get("name", ""))
                    )

    for p in _doctl_json(["projects", "list"], env):
        if p.get("name") == project_name:
            project_resources = _doctl_json(["projects", "resources", "list", p["id"]], env)
            if not project_resources:
                result.project_id = p["id"]
                result.project_name = p["name"]
            break

    return result


def delete_orphan(orphan: OrphanedResource, env: dict[str, str]) -> None:
    args_by_kind = {
        "load_balancer": ["compute", "load-balancer", "delete", orphan.id, "--force"],
        "volume": ["compute", "volume", "delete", orphan.id, "--force"],
        "firewall": ["compute", "firewall", "delete", orphan.id, "--force"],
    }
    code, _, stderr = capture(["doctl", *args_by_kind[orphan.kind]], env=env)
    if code != 0:
        _out.print(
            f"[yellow]Failed to delete {orphan.kind} {orphan.id} ({orphan.name}): "
            f"{stderr.strip()}[/yellow]"
        )


def delete_project(project_id: str, env: dict[str, str]) -> None:
    code, _, stderr = capture(
        ["doctl", "projects", "delete", project_id, "--force"], env=env
    )
    if code != 0:
        _out.print(f"[yellow]Failed to delete project {project_id}: {stderr.strip()}[/yellow]")

"""Typer entry point: create / destroy / status."""

from __future__ import annotations

import sys
import time

import questionary
import typer
from rich.console import Console

from . import doctl, flux, tailscale, tofu
from .config import load_config
from .env import ensure_tools, get_origin_repo, load_env
from .runner import capture, stream
from .status import show_status

app = typer.Typer(no_args_is_help=True, help="doks-flux-demo CLI: provision and operate the demo cluster.")

_out = Console()
_config = load_config()
_GIT_BRANCH = "main"
_CLUSTER_READY_TIMEOUT = 600.0
_CLUSTER_POLL_INTERVAL = 10.0


def _confirm(message: str, *, default: bool = True) -> bool:
    if not sys.stdin.isatty():
        return False
    answer = questionary.confirm(message, default=default).ask()
    if answer is None:
        raise typer.Exit(0)
    return bool(answer)


def _wait_for_cluster_running(env: dict[str, str]) -> None:
    deadline = time.monotonic() + _CLUSTER_READY_TIMEOUT
    _out.print(f"Waiting for cluster '{_config.cluster_name}' to reach running state...")
    while time.monotonic() < deadline:
        status = doctl.get_cluster_status(_config.cluster_name, env)
        if status == "running":
            _out.print(f"[green]Cluster '{_config.cluster_name}' is running.[/green]")
            return
        if status in ("error", "deleted"):
            _out.print(f"[red]Cluster entered unexpected state: {status}[/red]")
            raise typer.Exit(1)
        time.sleep(_CLUSTER_POLL_INTERVAL)
    _out.print(f"[red]Timed out waiting for cluster '{_config.cluster_name}' to reach running state.[/red]")
    raise typer.Exit(1)


def _save_kubeconfig(env: dict[str, str]) -> None:
    code = stream(
        ["doctl", "kubernetes", "cluster", "kubeconfig", "save", _config.cluster_name],
        env=env,
    )
    if code != 0:
        _out.print("[red]Failed to save kubeconfig.[/red]")
        raise typer.Exit(1)


def _print_tailnet_url(env: dict[str, str]) -> None:
    """Poll for the Tailscale ingress hostname and print it. The operator typically
    takes 30-60 seconds after the Ingress is created to provision the tailnet
    machine and write back the hostname."""
    _out.print()
    _out.print("Waiting for Tailscale to publish the ingress hostname...")
    deadline = time.monotonic() + 120.0
    while time.monotonic() < deadline:
        code, stdout, _ = capture(
            [
                "kubectl", "-n", "uptime-kuma-cloud", "get",
                "ingress/uptime-kuma-cloud-tailscale",
                "-o", "jsonpath={.status.loadBalancer.ingress[0].hostname}",
            ],
            env=env,
        )
        host = stdout.strip()
        if code == 0 and host:
            _out.print(f"[bold green]uptime-kuma is available at:[/bold green] https://{host}")
            _out.print("[dim](you must be on your tailnet to reach it)[/dim]")
            return
        time.sleep(5.0)
    _out.print(
        "[yellow]Ingress hostname not yet assigned after 2 minutes. "
        "Run `kubectl -n uptime-kuma-cloud get ingress` to check; "
        "the operator may still be provisioning.[/yellow]"
    )


@app.command()
def create(
    force: bool = typer.Option(
        False, "--force", help="Skip confirmation prompts (required for non-interactive use)."
    ),
) -> None:
    """Provision DOKS, bootstrap Flux, deploy Tailscale operator and uptime-kuma."""
    interactive = sys.stdin.isatty()
    if not interactive and not force:
        _out.print("[red]Cannot run interactively (not a TTY). Use --force.[/red]")
        raise typer.Exit(1)

    ensure_tools()
    user_env = load_env()
    child_env = user_env.child_env()
    owner, repo = get_origin_repo()

    _out.print(f"Checking for existing cluster '{_config.cluster_name}'...")
    existing = doctl.get_cluster_info(_config.cluster_name, child_env)
    if existing:
        _out.print(
            f"[yellow]Cluster '{_config.cluster_name}' already exists "
            f"({existing.uuid}, {existing.region}, {existing.status}).[/yellow]"
        )
        if not force and not _confirm("Run apply to sync infrastructure and re-bootstrap?"):
            raise typer.Exit(0)

    _out.print()
    _out.print("[bold]Planning infrastructure changes...[/bold]")
    plan_text = tofu.run_plan(child_env)
    plan = tofu.parse_plan(plan_text)

    if plan.no_changes:
        _out.print("[green]No infrastructure changes needed.[/green]")
    else:
        tofu.display_plan(plan)
        _out.print()
        if not force and not _confirm("Apply these changes?"):
            raise typer.Exit(0)
        _out.print()
        _out.print("[bold]Applying infrastructure changes...[/bold]")
        tofu.run_apply(child_env)

    _out.print()
    _wait_for_cluster_running(child_env)

    _out.print()
    _out.print("[bold]Saving kubeconfig...[/bold]")
    _save_kubeconfig(child_env)

    _out.print()
    if flux.is_bootstrapped(child_env):
        _out.print("[dim]Flux already bootstrapped, skipping.[/dim]")
    else:
        _out.print(f"[bold]Bootstrapping Flux against {owner}/{repo}...[/bold]")
        flux.bootstrap(owner, repo, _GIT_BRANCH, child_env)

    _out.print()
    _out.print("[bold]Waiting for infra-edge phase...[/bold]")
    flux.wait_for_kustomization("infra-edge", child_env)
    flux.wait_for_namespace("tailscale", child_env)

    _out.print("Applying tailscale/operator-oauth secret from .env...")
    tailscale.apply_operator_oauth(
        user_env.ts_client_id, user_env.ts_client_secret, child_env
    )

    _out.print()
    _out.print("[bold]Reconciling infra-edge...[/bold]")
    flux.reconcile_kustomization("infra-edge", child_env)
    flux.wait_for_kustomization_ready("infra-edge", child_env)

    _out.print()
    _out.print("[bold]Reconciling apps-uptime-kuma...[/bold]")
    flux.wait_for_kustomization("apps-uptime-kuma", child_env)
    flux.reconcile_kustomization("apps-uptime-kuma", child_env)
    flux.wait_for_kustomization_ready("apps-uptime-kuma", child_env)

    _out.print()
    _out.print("[green]Bootstrap complete.[/green]")
    _print_tailnet_url(child_env)


@app.command()
def destroy(
    force: bool = typer.Option(
        False, "--force", help="Skip confirmation prompts."
    ),
) -> None:
    """Tear down: suspend Flux, delete app + infra, terragrunt destroy, clean up DO + tailnet orphans."""
    interactive = sys.stdin.isatty()
    if not interactive and not force:
        _out.print("[red]Cannot run interactively (not a TTY). Use --force.[/red]")
        raise typer.Exit(1)

    ensure_tools()
    user_env = load_env()
    child_env = user_env.child_env()

    info = doctl.get_cluster_info(_config.cluster_name, child_env)
    if info:
        _out.print(
            f"Cluster '{_config.cluster_name}' exists "
            f"({info.uuid}, {info.region}, {info.status})."
        )
        if not force and not _confirm("Destroy the cluster and all its DO resources?", default=False):
            raise typer.Exit(0)
        cluster_uuid = info.uuid

        _out.print()
        _out.print("[bold]Saving kubeconfig for cluster access...[/bold]")
        _save_kubeconfig(child_env)

        _out.print()
        _out.print("[bold]Suspending Flux and deleting Kustomizations in reverse order...[/bold]")
        for name in ("apps-uptime-kuma-backups", "apps-uptime-kuma", "infra-edge", "flux-system"):
            flux.suspend_kustomization(name, child_env)
        for name in ("apps-uptime-kuma-backups", "apps-uptime-kuma", "infra-edge"):
            flux.delete_kustomization(name, child_env)

        _out.print()
        _out.print("[bold]Running terragrunt destroy...[/bold]")
        tofu.run_destroy(child_env)
    else:
        _out.print(
            f"[dim]Cluster '{_config.cluster_name}' not found via doctl. "
            f"Running terragrunt destroy and orphan audit anyway.[/dim]"
        )
        cluster_uuid = None
        try:
            tofu.run_destroy(child_env)
        except SystemExit:
            _out.print("[yellow]terragrunt destroy reported errors; continuing to audit.[/yellow]")

    _out.print()
    _out.print("[bold]Auditing DigitalOcean for orphaned resources...[/bold]")
    audit = doctl.audit_orphans(cluster_uuid, _config.project_name, child_env)

    if audit.cluster_exists:
        _out.print("[yellow]Cluster still exists; skipping orphan audit.[/yellow]")
        return

    if audit.orphans or audit.project_id:
        for orphan in audit.orphans:
            _out.print(f"  Orphan {orphan.kind}: {orphan.id} ({orphan.name})")
        if audit.project_id:
            _out.print(f"  Empty project: {audit.project_name} ({audit.project_id})")

        if force or _confirm("Delete these orphaned DO resources?", default=True):
            for orphan in audit.orphans:
                _out.print(f"Deleting {orphan.kind} {orphan.id}...")
                doctl.delete_orphan(orphan, child_env)
            if audit.project_id:
                _out.print(f"Deleting empty project {audit.project_name}...")
                doctl.delete_project(audit.project_id, child_env)
    else:
        _out.print("[green]No DO orphans found.[/green]")

    _out.print()
    _out.print("[bold]Auditing Tailscale tailnet for demo devices...[/bold]")
    ts_devices = tailscale.list_orphan_devices(
        user_env.ts_client_id, user_env.ts_client_secret
    )
    if ts_devices:
        for d in ts_devices:
            _out.print(f"  Tailnet device: {d.hostname} ({d.id}) tags={list(d.tags)}")
        if force or _confirm("Delete these tailnet devices?", default=True):
            for d in ts_devices:
                _out.print(f"Deleting tailnet device {d.hostname}...")
                tailscale.delete_device(d, user_env.ts_client_id, user_env.ts_client_secret)
    else:
        _out.print("[dim]No demo-related tailnet devices found.[/dim]")

    _out.print()
    _out.print("[green]Teardown complete.[/green]")
    _out.print(
        "[dim]Flux deploy keys on your GitHub fork are not auto-removed. "
        "Clean them up at https://github.com/<owner>/<repo>/settings/keys[/dim]"
    )


@app.command()
def status() -> None:
    """Show cluster, Flux, and workload health."""
    ensure_tools()
    user_env = load_env()
    child_env = user_env.child_env()
    show_status(_config.cluster_name, child_env)


if __name__ == "__main__":
    app()

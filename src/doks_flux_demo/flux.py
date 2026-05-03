"""Flux bootstrap, reconcile, and wait helpers."""

from __future__ import annotations

import time

from rich.console import Console

from .paths import FLUX_PATH
from .runner import capture, stream

_out = Console()
_WAIT_DELAY = 2.0
_WAIT_TIMEOUT = 600.0


def is_bootstrapped(env: dict[str, str]) -> bool:
    code, _, _ = capture(
        [
            "kubectl", "-n", "flux-system", "get",
            "kustomization.kustomize.toolkit.fluxcd.io/flux-system",
        ],
        env=env,
    )
    return code == 0


def bootstrap(owner: str, repo: str, branch: str, env: dict[str, str]) -> None:
    code = stream(
        [
            "flux", "bootstrap", "github",
            "--owner", owner,
            "--repository", repo,
            "--branch", branch,
            "--path", FLUX_PATH,
            "--personal",
            "--private",
        ],
        env=env,
    )
    if code != 0:
        _out.print("[red]flux bootstrap failed.[/red]")
        raise SystemExit(1)


def reconcile_source(env: dict[str, str]) -> None:
    stream(
        ["flux", "reconcile", "source", "git", "flux-system", "-n", "flux-system"],
        env=env,
    )


def reconcile_kustomization(name: str, env: dict[str, str]) -> None:
    code = stream(
        ["flux", "reconcile", "kustomization", name, "--with-source", "-n", "flux-system"],
        env=env,
    )
    if code != 0:
        _out.print(f"[red]flux reconcile kustomization {name} failed.[/red]")
        raise SystemExit(1)


def wait_for_kustomization(name: str, env: dict[str, str]) -> None:
    """Wait for a Kustomization to exist (be applied), not necessarily ready."""
    deadline = time.monotonic() + _WAIT_TIMEOUT
    while time.monotonic() < deadline:
        code, _, _ = capture(
            [
                "kubectl", "-n", "flux-system", "get",
                f"kustomization.kustomize.toolkit.fluxcd.io/{name}",
            ],
            env=env,
        )
        if code == 0:
            return
        time.sleep(_WAIT_DELAY)
    _out.print(f"[red]Timed out waiting for Kustomization '{name}' to appear.[/red]")
    raise SystemExit(1)


def wait_for_kustomization_ready(name: str, env: dict[str, str]) -> None:
    code = stream(
        [
            "kubectl", "-n", "flux-system", "wait",
            "--for=condition=Ready",
            f"kustomization.kustomize.toolkit.fluxcd.io/{name}",
            "--timeout=10m",
        ],
        env=env,
    )
    if code != 0:
        _out.print(f"[red]Kustomization '{name}' did not become Ready.[/red]")
        raise SystemExit(1)


def wait_for_namespace(name: str, env: dict[str, str]) -> None:
    deadline = time.monotonic() + _WAIT_TIMEOUT
    while time.monotonic() < deadline:
        code, _, _ = capture(["kubectl", "get", "namespace", name], env=env)
        if code == 0:
            return
        time.sleep(_WAIT_DELAY)
    _out.print(f"[red]Timed out waiting for namespace '{name}'.[/red]")
    raise SystemExit(1)


def suspend_kustomization(name: str, env: dict[str, str]) -> None:
    capture(["flux", "suspend", "kustomization", name, "-n", "flux-system"], env=env)


def delete_kustomization(name: str, env: dict[str, str]) -> None:
    """Delete a Flux Kustomization, allowing finalizers to clean up."""
    stream(
        [
            "kubectl", "-n", "flux-system", "delete",
            f"kustomization.kustomize.toolkit.fluxcd.io/{name}",
            "--ignore-not-found",
            "--timeout=5m",
        ],
        env=env,
    )

"""Apply the Tailscale operator OAuth secret directly from .env."""

from __future__ import annotations

from rich.console import Console

from .runner import stream

_out = Console()


def apply_operator_oauth(client_id: str, client_secret: str, env: dict[str, str]) -> None:
    """Create or update tailscale/operator-oauth from .env values."""
    manifest = (
        "apiVersion: v1\n"
        "kind: Secret\n"
        "metadata:\n"
        "  name: operator-oauth\n"
        "  namespace: tailscale\n"
        "type: Opaque\n"
        "stringData:\n"
        f"  client_id: {client_id}\n"
        f"  client_secret: {client_secret}\n"
    )
    code = stream(["kubectl", "apply", "-f", "-"], env=env, input_text=manifest)
    if code != 0:
        _out.print("[red]Failed to apply tailscale/operator-oauth secret.[/red]")
        raise SystemExit(1)

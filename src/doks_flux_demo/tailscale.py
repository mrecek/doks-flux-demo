"""Tailscale operator OAuth bootstrap and tailnet device cleanup."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from rich.console import Console

from .runner import stream

_out = Console()

_API_BASE = "https://api.tailscale.com/api/v2"
_HTTP_TIMEOUT = 30.0
# DELETE on the Tailscale API is documented as synchronous, but a defensive
# verification (parallel to the DigitalOcean drain check) catches partial
# successes — e.g., a delete that returned 200 but left the device visible.
_VERIFY_ATTEMPTS = 3
_VERIFY_DELAY = 2.0

# Demo-specific device names. These mirror values in the manifests:
#   - kubernetes/clusters/doks/infrastructure/edge/tailscale/helmrelease.yaml
#       (operatorConfig.hostname)
#   - kubernetes/clusters/doks/apps/uptime-kuma-cloud/ingress-tailscale.yaml
#       (spec.tls.hosts[0])
# Update both sides if either is renamed.
_OPERATOR_HOSTNAME = "doks-flux-demo-operator"
_PROXY_HOSTNAME_PREFIX = "uptime-kuma-demo"


@dataclass(frozen=True)
class TailscaleDevice:
    id: str
    hostname: str
    name: str
    tags: tuple[str, ...]
    last_seen: str


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


def list_orphan_devices(client_id: str, client_secret: str) -> list[TailscaleDevice]:
    """Return offline tailnet devices that match this demo's operator/proxy names.

    Online devices are skipped on the assumption they belong to a still-running
    cluster sharing the same naming. Returns [] on any API error.
    """
    try:
        token = _fetch_token(client_id, client_secret)
        # ?fields=all is required for the `online` field; without it the API
        # omits it and our offline filter would silently treat every device
        # as eligible for deletion.
        payload = _api_get("/tailnet/-/devices?fields=all", token)
    except (urllib.error.URLError, ValueError, KeyError) as exc:
        _out.print(f"[yellow]Tailnet device audit skipped: {exc}[/yellow]")
        return []

    out: list[TailscaleDevice] = []
    for raw in payload.get("devices", []):
        # Tailscale's API returns connectedToControl as the active-connection
        # indicator. Conservative: only consider deletion when the field is
        # explicitly False. True or missing -> skip, so we never touch a device
        # a co-tenant cluster (e.g. a sibling homelab) is actively using.
        if raw.get("connectedToControl") is not False:
            continue
        if not _matches_demo(raw):
            continue
        out.append(
            TailscaleDevice(
                id=raw.get("id", ""),
                hostname=raw.get("hostname", ""),
                name=raw.get("name", ""),
                tags=tuple(raw.get("tags", [])),
                last_seen=raw.get("lastSeen", ""),
            )
        )
    return out


def delete_device(device: TailscaleDevice, client_id: str, client_secret: str) -> bool:
    """Delete a tailnet device and verify it is gone. Returns True on success."""
    try:
        token = _fetch_token(client_id, client_secret)
        _api_delete(f"/device/{device.id}", token)
    except urllib.error.HTTPError as exc:
        _out.print(
            f"[yellow]Failed to delete tailnet device {device.hostname} "
            f"({device.id}): HTTP {exc.code}[/yellow]"
        )
        return False
    except urllib.error.URLError as exc:
        _out.print(
            f"[yellow]Failed to delete tailnet device {device.hostname} "
            f"({device.id}): {exc}[/yellow]"
        )
        return False

    for _ in range(_VERIFY_ATTEMPTS):
        try:
            _api_get(f"/device/{device.id}", token)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return True
            _out.print(
                f"[yellow]Could not verify tailnet device {device.hostname} "
                f"deletion: HTTP {exc.code}[/yellow]"
            )
            return True
        except urllib.error.URLError:
            return True
        time.sleep(_VERIFY_DELAY)

    _out.print(
        f"[yellow]Tailnet device {device.hostname} ({device.id}) still visible "
        f"after delete; check the Tailscale admin.[/yellow]"
    )
    return False


def _matches_demo(raw: dict) -> bool:
    hostname = raw.get("hostname", "")
    tags = raw.get("tags", [])
    if hostname == _OPERATOR_HOSTNAME and "tag:k8s-operator" in tags:
        return True
    if hostname.startswith(_PROXY_HOSTNAME_PREFIX) and "tag:k8s" in tags:
        return True
    return False


def _fetch_token(client_id: str, client_secret: str) -> str:
    body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode()
    req = urllib.request.Request(
        f"{_API_BASE}/oauth/token",
        data=body,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        return json.loads(resp.read())["access_token"]


def _api_get(path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{_API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        return json.loads(resp.read())


def _api_delete(path: str, token: str) -> None:
    req = urllib.request.Request(
        f"{_API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        method="DELETE",
    )
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT):
        pass

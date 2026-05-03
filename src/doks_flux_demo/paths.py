"""Project layout constants."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOFU_DEPLOYMENT = PROJECT_ROOT / "tofu" / "deployments" / "doks"
FLUX_PATH = "kubernetes/clusters/doks"
CLUSTER_KUSTOMIZATION = PROJECT_ROOT / "kubernetes" / "clusters" / "doks" / "kustomization.yaml"

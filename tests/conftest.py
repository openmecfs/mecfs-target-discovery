"""Shared pytest fixtures."""
from __future__ import annotations

from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def loci_json_path(project_root: Path) -> Path:
    return project_root / "data" / "decodeme" / "loci.json"


@pytest.fixture
def ot_cache_dir(project_root: Path, tmp_path: Path, monkeypatch) -> Path:
    """Redirect Open Targets cache to a temp dir for tests."""
    import src.connectors.open_targets as ot_mod
    monkeypatch.setattr(ot_mod, "CACHE_DIR", tmp_path / "ot_cache")
    return tmp_path / "ot_cache"

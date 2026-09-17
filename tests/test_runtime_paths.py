"""``app.utils.runtime_paths.app_root`` : résolution des chemins non-Python
embarqués, valable en développement comme dans un exécutable PyInstaller
(§2/§11 du cahier des charges de la phase Packaging)."""
from pathlib import Path

import pytest

from app.utils import runtime_paths


def test_app_root_in_development_mode_is_the_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr("sys.frozen", raising=False)

    root = runtime_paths.app_root()

    assert (root / "app").is_dir()
    assert (root / "alembic.ini").is_file()
    assert (root / "migrations").is_dir()


def test_app_root_when_frozen_uses_meipass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)

    root = runtime_paths.app_root()

    assert root == tmp_path


def test_app_root_when_frozen_without_meipass_falls_back_to_executable_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Cas onefile théorique où _MEIPASS ne serait pas positionnée : ne doit
    jamais lever, retombe sur le dossier de l'exécutable."""
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.delattr("sys._MEIPASS", raising=False)
    fake_executable = tmp_path / "StockManager.exe"
    monkeypatch.setattr("sys.executable", str(fake_executable))

    root = runtime_paths.app_root()

    assert root == tmp_path

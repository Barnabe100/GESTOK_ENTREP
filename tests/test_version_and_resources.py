"""Version applicative centralisée (§17) et résolution des ressources
embarquées (§11) — voir app/version.py et app/utils/runtime_paths.py."""
import re
import tomllib
from pathlib import Path

from app.resources import APP_ICON_PATH, APP_STYLESHEET_PATH, load_stylesheet
from app.version import APP_NAME, __version__

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_version_follows_semantic_versioning_format() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_pyproject_version_matches_app_version() -> None:
    """app/version.py est la source unique (§17) : pyproject.toml — simple
    métadonnée [project], non lue par PyInstaller/Inno Setup/l'application —
    doit néanmoins rester alignée pour éviter toute confusion (Lot J)."""
    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == __version__


def test_app_name_is_non_empty() -> None:
    assert APP_NAME.strip() != ""


def test_stylesheet_and_icon_resolve_to_real_files() -> None:
    assert APP_STYLESHEET_PATH.is_file()
    assert APP_ICON_PATH.is_file()


def test_load_stylesheet_returns_non_empty_text() -> None:
    content = load_stylesheet()
    assert isinstance(content, str)
    assert content.strip() != ""

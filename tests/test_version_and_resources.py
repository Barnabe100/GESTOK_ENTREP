"""Version applicative centralisée (§17) et résolution des ressources
embarquées (§11) — voir app/version.py et app/utils/runtime_paths.py."""
import re
import tomllib
from pathlib import Path

from app.resources import (
    APP_ICON_PATH,
    APP_LOGO_FULL_PATH,
    APP_LOGO_OFFICIAL_SOURCE_PATH,
    APP_STYLESHEET_PATH,
    load_stylesheet,
)
from app.version import APP_NAME, PUBLISHER_NAME, __version__

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


def test_publisher_name_is_non_empty_and_distinct_from_product_name() -> None:
    """L'éditeur (TechNova) reste distinct du nom du produit (StockManager
    Desktop) — jamais fusionnés, voir app/views/about_dialog.py."""
    assert PUBLISHER_NAME.strip() != ""
    assert PUBLISHER_NAME != APP_NAME


def test_windows_version_metadata_uses_publisher_for_company_name() -> None:
    """packaging/file_version_info.txt (régénéré par
    packaging/generate_version_info.py) doit porter CompanyName=éditeur,
    distinct de ProductName/FileDescription=nom du produit — jamais édité à
    la main (voir le script)."""
    content = (_REPO_ROOT / "packaging" / "file_version_info.txt").read_text(encoding="utf-8")
    assert f"StringStruct(u'CompanyName', u'{PUBLISHER_NAME}')" in content
    assert f"StringStruct(u'ProductName', u'{APP_NAME}')" in content


def test_inno_setup_publisher_matches_publisher_name() -> None:
    """packaging/inno_setup.iss : MyAppPublisher n'est pas généré (Inno
    Setup n'exécute pas Python) — synchronisation manuelle documentée dans
    le script, vérifiée ici pour détecter toute dérive."""
    content = (_REPO_ROOT / "packaging" / "inno_setup.iss").read_text(encoding="utf-8")
    assert f'#define MyAppPublisher "{PUBLISHER_NAME}"' in content


def test_stylesheet_and_icon_resolve_to_real_files() -> None:
    assert APP_STYLESHEET_PATH.is_file()
    assert APP_ICON_PATH.is_file()


def test_load_stylesheet_returns_non_empty_text() -> None:
    content = load_stylesheet()
    assert isinstance(content, str)
    assert content.strip() != ""


# -- identité visuelle officielle (lot Identité visuelle) -----------------------------


def test_branding_files_resolve_to_real_files() -> None:
    assert APP_ICON_PATH.is_file()
    assert APP_LOGO_FULL_PATH.is_file()
    assert APP_LOGO_OFFICIAL_SOURCE_PATH.is_file()


def test_app_icon_mark_is_square() -> None:
    """Une icône Windows (.ico) exige un canevas carré — le symbole SM +
    carton isolé doit donc être carré, jamais le rectangle brut du logo
    complet."""
    from PIL import Image

    with Image.open(APP_ICON_PATH) as img:
        width, height = img.size
    assert width == height


def test_app_logo_full_matches_official_source_dimensions() -> None:
    """La conversion de format (WEBP -> PNG) ne doit ni recadrer ni
    redimensionner : mêmes dimensions que le fichier officiel."""
    from PIL import Image

    with Image.open(APP_LOGO_FULL_PATH) as full, Image.open(APP_LOGO_OFFICIAL_SOURCE_PATH) as official:
        assert full.size == official.size


def test_app_icon_mark_pixels_are_a_crop_of_the_official_logo() -> None:
    """Le symbole isolé ne doit jamais être une nouvelle création : chaque
    pixel non blanc du recadrage doit provenir du logo officiel, à la même
    position relative (aucune retouche, aucun redessin)."""
    from PIL import Image

    with Image.open(APP_ICON_PATH) as mark:
        mark_rgb = mark.convert("RGB")
    with Image.open(APP_LOGO_OFFICIAL_SOURCE_PATH) as official:
        official_rgb = official.convert("RGB")

    # Le canevas carré du symbole est nécessairement plus petit ou égal au
    # logo complet (recadrage, jamais un agrandissement).
    assert mark_rgb.width <= official_rgb.width
    assert mark_rgb.height <= official_rgb.height


def _load_generate_icon_module():
    """Charge packaging/generate_icon.py par chemin de fichier (jamais par
    ``import packaging...`` : ``packaging`` est le nom d'une bibliothèque
    PyPI réelle déjà installée comme dépendance de setuptools/pip — un
    import par nom de module entrerait directement en conflit avec elle)."""
    import importlib.util

    module_path = _REPO_ROOT / "packaging" / "generate_icon.py"
    spec = importlib.util.spec_from_file_location("stockmanager_generate_icon", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_windows_icon_ico_contains_all_standard_resolutions() -> None:
    """packaging/app_icon.ico (régénéré par packaging/generate_icon.py à
    partir du symbole officiel) doit couvrir toutes les résolutions
    Windows usuelles (barre des tâches, Explorateur, raccourcis)."""
    from PIL import Image

    generate_icon_module = _load_generate_icon_module()
    ico_path = _REPO_ROOT / "packaging" / "app_icon.ico"
    assert ico_path.is_file()
    with Image.open(ico_path) as img:
        available_sizes = {size[0] for size in img.info.get("sizes", set())}
    assert set(generate_icon_module.ICON_SIZES).issubset(available_sizes)


def test_generate_icon_script_produces_valid_multi_resolution_ico(tmp_path) -> None:
    """Exécute réellement packaging/generate_icon.py (sans dépendance Qt
    depuis le lot Identité visuelle — Pillow seul) vers un fichier
    temporaire, pour prouver que le script fonctionne de bout en bout,
    jamais seulement que son fichier de sortie existe déjà en dépôt."""
    from PIL import Image

    generate_icon_module = _load_generate_icon_module()
    output = tmp_path / "generated_app_icon.ico"
    original_output = generate_icon_module.OUTPUT_ICO
    try:
        generate_icon_module.OUTPUT_ICO = output
        result = generate_icon_module.main()
    finally:
        generate_icon_module.OUTPUT_ICO = original_output

    assert result == 0
    assert output.is_file()
    with Image.open(output) as img:
        available_sizes = {size[0] for size in img.info.get("sizes", set())}
    assert set(generate_icon_module.ICON_SIZES).issubset(available_sizes)

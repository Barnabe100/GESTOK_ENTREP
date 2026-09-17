from pathlib import Path

RESOURCES_DIR = Path(__file__).resolve().parent
STYLES_DIR = RESOURCES_DIR / "styles"
ICONS_DIR = RESOURCES_DIR / "icons"

APP_STYLESHEET_PATH = STYLES_DIR / "app.qss"
APP_ICON_PATH = ICONS_DIR / "app_icon.svg"


def load_stylesheet() -> str:
    """Charge la feuille de style Qt principale de l'application."""
    return APP_STYLESHEET_PATH.read_text(encoding="utf-8")

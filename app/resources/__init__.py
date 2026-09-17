from app.utils.runtime_paths import app_root

# Résolu depuis la racine applicative plutôt que ``Path(__file__).parent`` :
# reste valable une fois packagé par PyInstaller, où ``__file__`` ne
# correspond plus à un fichier réel sur disque (voir runtime_paths.py).
RESOURCES_DIR = app_root() / "app" / "resources"
STYLES_DIR = RESOURCES_DIR / "styles"
ICONS_DIR = RESOURCES_DIR / "icons"

APP_STYLESHEET_PATH = STYLES_DIR / "app.qss"
APP_ICON_PATH = ICONS_DIR / "app_icon.svg"


def load_stylesheet() -> str:
    """Charge la feuille de style Qt principale de l'application."""
    return APP_STYLESHEET_PATH.read_text(encoding="utf-8")

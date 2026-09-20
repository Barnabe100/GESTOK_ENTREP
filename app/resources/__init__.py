from app.utils.runtime_paths import app_root

# Résolu depuis la racine applicative plutôt que ``Path(__file__).parent`` :
# reste valable une fois packagé par PyInstaller, où ``__file__`` ne
# correspond plus à un fichier réel sur disque (voir runtime_paths.py).
RESOURCES_DIR = app_root() / "app" / "resources"
STYLES_DIR = RESOURCES_DIR / "styles"
BRANDING_DIR = RESOURCES_DIR / "branding"

APP_STYLESHEET_PATH = STYLES_DIR / "app.qss"

# Identité visuelle officielle StockManager/SM (lot Identité visuelle) —
# dérivée du logo officiel fourni par le client, jamais redessinée :
# - APP_ICON_PATH : symbole SM + carton isolé (sans texte ni slogan), pour
#   l'icône d'application (fenêtre, barre des tâches, EXE, installateur) ;
#   généré par un simple recadrage technique du logo officiel, voir
#   ``app/resources/branding/README.md``.
# - APP_LOGO_FULL_PATH : logo complet (symbole + texte + slogan), pour les
#   emplacements affichant l'identité complète du produit (ex. À propos).
# - APP_LOGO_OFFICIAL_SOURCE_PATH : fichier officiel fourni par le client,
#   conservé tel quel (archive de référence), jamais utilisé directement au
#   runtime (format WEBP non garanti disponible dans un exécutable
#   PyInstaller packagé sans le plugin Qt correspondant).
APP_ICON_PATH = BRANDING_DIR / "stockmanager_mark.png"
APP_LOGO_FULL_PATH = BRANDING_DIR / "stockmanager_logo_full.png"
APP_LOGO_OFFICIAL_SOURCE_PATH = BRANDING_DIR / "stockmanager_logo_official.webp"


def load_stylesheet() -> str:
    """Charge la feuille de style Qt principale de l'application."""
    return APP_STYLESHEET_PATH.read_text(encoding="utf-8")

# Identité visuelle officielle — StockManager / TechNova

Ce dossier contient l'identité visuelle officielle du produit, fournie par
le client (jamais fabriquée ni redessinée par le développement). Distinct
du logo de l'entreprise cliente (géré par `CompanySettingsService`, stocké
dans le répertoire de données utilisateur, jamais dans `app/resources`).

## Fichiers

- **`stockmanager_logo_official.webp`** — fichier source officiel fourni
  par le client, conservé tel quel (archive de référence). Jamais utilisé
  directement au runtime : le format WEBP n'est pas garanti disponible
  dans un exécutable PyInstaller packagé (plugin Qt non systématiquement
  embarqué), voir `app/resources/__init__.py`.
- **`stockmanager_logo_full.png`** — conversion de format sans perte du
  fichier officiel (mêmes pixels, aucun recadrage), utilisée partout où
  l'identité complète du produit doit être affichée (ex. dialogue
  « À propos »).
- **`stockmanager_mark.png`** — symbole SM + carton isolé (sans le texte
  « StockManager » ni le slogan), utilisé pour l'icône applicative
  (fenêtre, barre des tâches, exécutable Windows, installateur). Obtenu
  par un recadrage technique du logo officiel : la limite de recadrage a
  été déterminée en détectant la zone de blanc séparant réellement le
  symbole du texte dans le fichier source (jamais une estimation visuelle
  approximative), puis complétée par un fond blanc (couleur de fond du
  logo source elle-même) pour obtenir un canevas carré, seul format
  utilisable pour une icône Windows. Aucun élément graphique n'a été
  ajouté, supprimé ou modifié à l'intérieur du symbole lui-même.

## Régénération de l'icône Windows

`packaging/app_icon.ico` est généré à partir de `stockmanager_mark.png`
par `packaging/generate_icon.py` — à relancer uniquement si ce fichier
source change :

```
python packaging/generate_icon.py
```

## Ne jamais

- Remplacer ces fichiers par un logo différent sans qu'un nouveau fichier
  officiel n'ait été explicitement fourni.
- Utiliser `stockmanager_logo_full.png` (avec texte/slogan) comme icône
  d'application — seul `stockmanager_mark.png` (symbole seul) convient à
  cet usage.
- Confondre ce dossier avec le logo de l'entreprise cliente (voir
  `app/services/settings/company_settings_service.py`).

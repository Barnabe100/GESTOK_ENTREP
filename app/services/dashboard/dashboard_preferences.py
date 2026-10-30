"""Préférences de personnalisation du Dashboard (Mission 3, §6.2-6.3) :
quels indicateurs (KPI) un utilisateur choisit d'afficher.

Stockage strictement LOCAL — jamais dans la base métier SQLite/PostgreSQL :
un simple fichier JSON dans le répertoire de données local de l'application
(``Settings.data_dir``, déjà utilisé pour les logs/le branding), à côté de
la configuration de connexion. Aucun mécanisme générique de préférences
utilisateur n'existe déjà en base, et cette personnalisation est
strictement un confort d'affichage, indépendant des données métier et des
permissions RBAC (§6.3) — introduire une migration pour ce seul besoin
n'est pas justifié. Conséquence assumée : les préférences restent propres
à ce poste, jamais synchronisées entre postes en configuration PostgreSQL
multi-poste — explicitement accepté par le cahier des charges (« si une
préférence locale par utilisateur connecté est suffisante... l'utiliser »).

Clé = nom d'utilisateur StockManager (jamais l'identifiant du compte du
système d'exploitation) : plusieurs utilisateurs StockManager partageant un
même poste (ex. caisse partagée) gardent chacun leur propre sélection.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.config.settings import Settings, get_settings

_PREFERENCES_FILENAME = "dashboard_preferences.json"


def _preferences_path(settings: Optional[Settings] = None) -> Path:
    settings = settings or get_settings()
    return settings.data_dir / _PREFERENCES_FILENAME


def _read_all(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_selected_kpis(username: str, settings: Optional[Settings] = None) -> Optional[list[str]]:
    """``None`` si l'utilisateur n'a jamais personnalisé son Dashboard (ou
    si le fichier est absent/corrompu) — jamais une liste vide qui
    masquerait silencieusement tous les indicateurs : l'appelant applique
    alors sa propre sélection par défaut."""
    data = _read_all(_preferences_path(settings))
    value = data.get(username)
    if not isinstance(value, list):
        return None
    return [str(v) for v in value]


def save_selected_kpis(username: str, kpi_ids: list[str], settings: Optional[Settings] = None) -> None:
    path = _preferences_path(settings)
    data = _read_all(path)
    data[username] = list(kpi_ids)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

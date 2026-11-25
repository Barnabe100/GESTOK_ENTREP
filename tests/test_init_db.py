"""Vérifie app.db.init_db.is_ancestor_revision — mission corrective
« Fiabilisation du module de sauvegarde », §3.10 (compatibilité de version
assouplie avant restauration)."""
from alembic.script import ScriptDirectory

from app.config.settings import Settings
from app.db.init_db import _alembic_config, is_ancestor_revision


def _current_head(settings: Settings) -> str:
    script = ScriptDirectory.from_config(_alembic_config(settings))
    heads = script.get_heads()
    assert len(heads) == 1, "l'historique de migrations de ce projet est censé être linéaire (une seule tête)."
    return heads[0]


def test_head_is_its_own_ancestor(test_settings) -> None:
    head = _current_head(test_settings)

    assert is_ancestor_revision(head, test_settings) is True


def test_the_very_first_revision_is_an_ancestor_of_head(test_settings) -> None:
    assert is_ancestor_revision("0001", test_settings) is True


def test_an_intermediate_revision_is_an_ancestor_of_head(test_settings) -> None:
    assert is_ancestor_revision("0010", test_settings) is True


def test_none_is_never_an_ancestor(test_settings) -> None:
    assert is_ancestor_revision(None, test_settings) is False


def test_empty_string_is_never_an_ancestor(test_settings) -> None:
    assert is_ancestor_revision("", test_settings) is False


def test_unknown_revision_is_never_an_ancestor(test_settings) -> None:
    """Couvre aussi bien une faute de frappe qu'une sauvegarde provenant
    d'une version FUTURE de StockManager (révision qui n'existe pas encore
    dans CET historique de migrations) — dans les deux cas, jamais une
    mise à niveau automatique sûre."""
    assert is_ancestor_revision("9999_ne_correspond_pas", test_settings) is False

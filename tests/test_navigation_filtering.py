"""Vérifie que la navigation affichée correspond exactement à la matrice
permissions -> rôles validée (voir app/db/seed.py)."""
from app.views.main_window import MainWindow

EXPECTED_MODULES_BY_ROLE = {
    "Administrateur": {
        "Dashboard", "Articles", "Catégories", "Fournisseurs", "Entrées", "Sorties",
        "Ventes", "Mouvements", "Inventaires", "Rapports", "Utilisateurs", "Paramètres",
    },
    "Gestionnaire de stock": {
        "Dashboard", "Articles", "Catégories", "Fournisseurs", "Entrées", "Sorties",
        "Mouvements", "Inventaires", "Rapports",
    },
    "Vendeur": {"Dashboard", "Articles", "Ventes"},
    "Consultation": {"Dashboard", "Articles", "Catégories", "Fournisseurs", "Mouvements", "Rapports"},
}


def test_administrateur_navigation_matches_full_access_matrix(qtbot, login_as) -> None:
    auth_service, permission_service, user_service, _ = login_as("Administrateur")
    window = MainWindow(auth_service, permission_service, user_service)
    qtbot.addWidget(window)
    assert set(window.visible_modules) == EXPECTED_MODULES_BY_ROLE["Administrateur"]


def test_gestionnaire_stock_navigation_excludes_ventes_utilisateurs_parametres(qtbot, login_as) -> None:
    auth_service, permission_service, user_service, _ = login_as("Gestionnaire de stock")
    window = MainWindow(auth_service, permission_service, user_service)
    qtbot.addWidget(window)

    assert set(window.visible_modules) == EXPECTED_MODULES_BY_ROLE["Gestionnaire de stock"]
    assert "Ventes" not in window.visible_modules
    assert "Utilisateurs" not in window.visible_modules
    assert "Paramètres" not in window.visible_modules


def test_vendeur_navigation_is_limited_to_dashboard_articles_ventes(qtbot, login_as) -> None:
    auth_service, permission_service, user_service, _ = login_as("Vendeur")
    window = MainWindow(auth_service, permission_service, user_service)
    qtbot.addWidget(window)

    assert set(window.visible_modules) == EXPECTED_MODULES_BY_ROLE["Vendeur"]
    assert "Utilisateurs" not in window.visible_modules
    assert "Paramètres" not in window.visible_modules  # pas d'accès aux sauvegardes/paramètres


def test_consultation_navigation_is_read_only_modules(qtbot, login_as) -> None:
    auth_service, permission_service, user_service, _ = login_as("Consultation")
    window = MainWindow(auth_service, permission_service, user_service)
    qtbot.addWidget(window)

    assert set(window.visible_modules) == EXPECTED_MODULES_BY_ROLE["Consultation"]
    assert "Ventes" not in window.visible_modules
    assert "Utilisateurs" not in window.visible_modules


def test_only_administrateur_sees_utilisateurs_module(qtbot, login_as) -> None:
    for role_name in ("Gestionnaire de stock", "Vendeur", "Consultation"):
        auth_service, permission_service, user_service, _ = login_as(role_name)
        window = MainWindow(auth_service, permission_service, user_service)
        qtbot.addWidget(window)
        assert "Utilisateurs" not in window.visible_modules

    auth_service, permission_service, user_service, _ = login_as("Administrateur")
    window = MainWindow(auth_service, permission_service, user_service)
    qtbot.addWidget(window)
    assert "Utilisateurs" in window.visible_modules


def test_vendeur_cannot_reach_backup_restore_or_license_pages(qtbot, login_as) -> None:
    """Le cahier des charges exige explicitement : pas d'accès à la restauration des
    sauvegardes ni à la gestion des licences pour le Vendeur. Ces modules ne sont pas
    encore dans la navigation (phases ultérieures) ; on vérifie ici l'équivalent
    actuellement pertinent : aucune permission BACKUP_RESTORE/LICENSE_* n'est accordée."""
    _, permission_service, _, _ = login_as("Vendeur")
    assert permission_service.has_permission("BACKUP_RESTORE") is False
    assert permission_service.has_permission("LICENSE_ACTIVATE") is False
    assert permission_service.has_permission("USER_VIEW") is False

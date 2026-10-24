"""Lot E (§E.2) : mécanique pure des sauvegardes/restaurations PostgreSQL —
voir ``app.services.backups.postgresql_backup_engine``.

Serveur PostgreSQL de test réel, même convention que les lots précédents
(``tests/test_db_session.py``, ``tests/test_database_admin_service.py``) :
si le serveur ou ``STOCKMANAGER_TEST_PG_PASSWORD`` ne sont pas disponibles,
ces tests sont ignorés proprement (``pytest.skip``), jamais présentés comme
un échec de l'application. Utilise exclusivement la base/le rôle de test
dédiés (``stockmanager_test``), jamais une base cliente — chaque test qui
modifie des données le fait sur une table ou des lignes qu'il crée et
nettoie lui-même."""
from __future__ import annotations

import contextlib
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Iterator

import psycopg
import pytest

from app.config.settings import PostgreSQLConnectionConfig, Settings
from app.db import session as db_session_module
from app.db.init_db import init_database
from app.services.backups import postgresql_backup_engine as eng

_PG_HOST = os.environ.get("STOCKMANAGER_TEST_PG_HOST", "127.0.0.1")
_PG_PORT = int(os.environ.get("STOCKMANAGER_TEST_PG_PORT", "5432"))
_PG_DB = os.environ.get("STOCKMANAGER_TEST_PG_DB", "stockmanager_test")
_PG_USER = os.environ.get("STOCKMANAGER_TEST_PG_USER", "stockmanager_test")
_PG_PASSWORD = os.environ.get("STOCKMANAGER_TEST_PG_PASSWORD")


@pytest.fixture()
def pg_target_and_password(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Garantit un schéma applicatif complet sur la base de test partagée,
    quel que soit l'état laissé par un test exécuté précédemment dans la
    même session (``tests/test_migrations_postgresql.py`` et
    ``tests/test_document_validation_concurrency_postgresql.py`` vident
    délibérément ce schéma pour leurs propres besoins — voir leurs
    fixtures) : ``init_database`` est idempotente, jamais destructive sur
    un schéma déjà complet."""
    if _PG_PASSWORD is None:
        pytest.skip(
            "STOCKMANAGER_TEST_PG_PASSWORD non défini : voir la documentation "
            "de ce lot pour configurer un serveur PostgreSQL de test."
        )
    target = eng.PostgreSQLTarget(host=_PG_HOST, port=_PG_PORT, database=_PG_DB, username=_PG_USER)
    password_env_var = f"__test_pg_backup_engine_{uuid.uuid4().hex}__"
    monkeypatch.setenv(password_env_var, _PG_PASSWORD)
    settings = Settings(
        environment="test", db_path=tmp_path / "unused-for-postgresql.db", log_dir=tmp_path / "logs",
        log_level="DEBUG", default_currency="XOF", db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(
            host=target.host, port=target.port, database=target.database, username=target.username,
            password_env_var=password_env_var, connect_timeout_seconds=5,
        ),
    )
    db_session_module.reset_engine_cache()
    try:
        init_database(settings)
    except Exception as exc:  # noqa: BLE001 - serveur injoignable -> skip, jamais un échec.
        db_session_module.reset_engine_cache()
        pytest.skip(f"Serveur PostgreSQL de test non atteignable ({_PG_HOST}:{_PG_PORT}) : {exc}")
    db_session_module.reset_engine_cache()
    return target, _PG_PASSWORD


def _scratch_table_name() -> str:
    return f"lot_e_scratch_{uuid.uuid4().hex[:8]}"


# -- vérification de la présence des outils ----------------------------------------


def test_ensure_tools_available_raises_when_both_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(eng.shutil, "which", lambda name: None)
    with pytest.raises(eng.PostgreSQLToolNotFoundError) as excinfo:
        eng.ensure_tools_available()
    assert "pg_dump" in str(excinfo.value)
    assert "pg_restore" in str(excinfo.value)


def test_ensure_tools_available_lists_only_the_missing_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    real_which = shutil.which
    monkeypatch.setattr(eng.shutil, "which", lambda name: None if name == "pg_restore" else real_which(name))
    with pytest.raises(eng.PostgreSQLToolNotFoundError) as excinfo:
        eng.ensure_tools_available()
    # Seule la liste des outils manquants (avant la phrase de conseil générale,
    # qui mentionne les deux noms par cohérence) doit ne citer que pg_restore.
    missing_list_clause = str(excinfo.value).split(".")[0]
    assert "pg_restore" in missing_list_clause
    assert "pg_dump" not in missing_list_clause


def test_ensure_tools_available_does_not_raise_when_present() -> None:
    """Suppose pg_dump/pg_restore installés dans l'environnement de test
    (voir le rapport de phase) — sinon ignoré."""
    if shutil.which("pg_dump") is None or shutil.which("pg_restore") is None:
        pytest.skip("pg_dump/pg_restore non installés dans cet environnement.")
    eng.ensure_tools_available()


def test_ensure_tools_available_returns_resolved_paths_not_bare_names() -> None:
    """Incident « détection pg_dump/pg_restore introuvables sous Windows » :
    le chemin résolu (et non le seul nom nu) doit être restitué, pour que
    l'outil réellement invoqué par les fonctions ci-dessous soit bien celui
    dont la présence a été vérifiée ici."""
    if shutil.which("pg_dump") is None or shutil.which("pg_restore") is None:
        pytest.skip("pg_dump/pg_restore non installés dans cet environnement.")
    resolved = eng.ensure_tools_available()
    assert resolved["pg_dump"] == shutil.which("pg_dump")
    assert resolved["pg_restore"] == shutil.which("pg_restore")


# -- repli Windows quand le PATH ne suffit pas (incident « pg_dump/pg_restore
# introuvables sous Windows ») : pg_dump.exe/pg_restore.exe réellement
# présents et utilisables à l'emplacement standard de l'installeur officiel,
# mais absents du PATH du processus (ex. service, PATH non mis à jour) --------


def test_locate_tool_falls_back_to_windows_standard_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(eng.shutil, "which", lambda name: None)
    monkeypatch.setattr(eng.platform, "system", lambda: "Windows")
    pg_root = tmp_path / "PostgreSQL"
    bin_dir = pg_root / "16" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "pg_dump.exe").write_text("")
    monkeypatch.setattr(eng, "_WINDOWS_PG_BASE_DIRS", (str(pg_root),))

    found = eng._locate_tool("pg_dump")

    assert found == bin_dir / "pg_dump.exe"


def test_locate_tool_prefers_the_highest_version_when_several_are_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§G : jamais une seule version codée en dur — plusieurs versions
    peuvent coexister sur le même poste."""
    monkeypatch.setattr(eng.shutil, "which", lambda name: None)
    monkeypatch.setattr(eng.platform, "system", lambda: "Windows")
    pg_root = tmp_path / "PostgreSQL"
    for version in ("13", "16", "9.6"):
        bin_dir = pg_root / version / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "pg_restore.exe").write_text("")
    monkeypatch.setattr(eng, "_WINDOWS_PG_BASE_DIRS", (str(pg_root),))

    found = eng._locate_tool("pg_restore")

    assert found == pg_root / "16" / "bin" / "pg_restore.exe"


def test_locate_tool_returns_none_when_absent_from_path_and_standard_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(eng.shutil, "which", lambda name: None)
    monkeypatch.setattr(eng.platform, "system", lambda: "Windows")
    monkeypatch.setattr(eng, "_WINDOWS_PG_BASE_DIRS", (str(tmp_path / "PostgreSQL"),))

    assert eng._locate_tool("pg_dump") is None


def test_locate_tool_never_searches_windows_directories_outside_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La recherche de repli reste strictement réservée à Windows — jamais
    une tentative sur un autre système, même si un répertoire portant ce
    nom existe fortuitement."""
    monkeypatch.setattr(eng.shutil, "which", lambda name: None)
    monkeypatch.setattr(eng.platform, "system", lambda: "Linux")
    pg_root = tmp_path / "PostgreSQL"
    bin_dir = pg_root / "16" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "pg_dump.exe").write_text("")
    monkeypatch.setattr(eng, "_WINDOWS_PG_BASE_DIRS", (str(pg_root),))

    assert eng._locate_tool("pg_dump") is None


def test_ensure_tools_available_succeeds_via_windows_fallback_when_path_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reproduit exactement le symptôme signalé : les deux outils sont
    réellement présents et exécutables à l'emplacement standard, absents
    du seul PATH — ne doit plus lever ``PostgreSQLToolNotFoundError``."""
    monkeypatch.setattr(eng.shutil, "which", lambda name: None)
    monkeypatch.setattr(eng.platform, "system", lambda: "Windows")
    pg_root = tmp_path / "PostgreSQL"
    bin_dir = pg_root / "16" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "pg_dump.exe").write_text("")
    (bin_dir / "pg_restore.exe").write_text("")
    monkeypatch.setattr(eng, "_WINDOWS_PG_BASE_DIRS", (str(pg_root),))

    resolved = eng.ensure_tools_available()

    assert resolved == {
        "pg_dump": str(bin_dir / "pg_dump.exe"),
        "pg_restore": str(bin_dir / "pg_restore.exe"),
    }


def test_ensure_tools_available_raises_when_absent_from_path_and_standard_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(eng.shutil, "which", lambda name: None)
    monkeypatch.setattr(eng.platform, "system", lambda: "Windows")
    monkeypatch.setattr(eng, "_WINDOWS_PG_BASE_DIRS", (str(tmp_path / "PostgreSQL"),))

    with pytest.raises(eng.PostgreSQLToolNotFoundError) as excinfo:
        eng.ensure_tools_available()
    assert "pg_dump" in str(excinfo.value)
    assert "pg_restore" in str(excinfo.value)


def test_verify_backup_file_uses_windows_fallback_path_for_pg_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le même repli doit s'appliquer à la vérification d'archive, pas
    seulement à la sauvegarde/restauration elle-même."""
    monkeypatch.setattr(eng.shutil, "which", lambda name: None)
    monkeypatch.setattr(eng.platform, "system", lambda: "Windows")
    pg_root = tmp_path / "PostgreSQL"
    bin_dir = pg_root / "16" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "pg_restore.exe").write_text("")
    monkeypatch.setattr(eng, "_WINDOWS_PG_BASE_DIRS", (str(pg_root),))

    captured_args = {}

    def _fake_run(args, **kwargs):
        captured_args["args"] = args
        raise OSError("simulation : exécution non pertinente pour ce test")

    monkeypatch.setattr(eng.subprocess, "run", _fake_run)

    fake_backup = tmp_path / "fake.dump"
    fake_backup.write_text("contenu factice")
    result = eng.verify_backup_file(fake_backup)

    assert captured_args["args"][0] == str(bin_dir / "pg_restore.exe")
    assert result.valid is False


# -- nommage et collision (aucun serveur requis) -----------------------------------


def test_generate_backup_filename_uses_dump_extension() -> None:
    from datetime import datetime

    name = eng.generate_backup_filename(when=datetime(2026, 1, 2, 3, 4, 5))
    assert name == "stockmanager_backup_pg_20260102_030405.dump"


def test_next_available_path_avoids_collision(tmp_path: Path) -> None:
    filename = "stockmanager_backup_pg_20260102_030405.dump"
    (tmp_path / filename).write_bytes(b"x")
    candidate = eng._next_available_path(tmp_path, filename)
    assert candidate.name == "stockmanager_backup_pg_20260102_030405_2.dump"


def test_list_backup_files_only_matches_postgresql_pattern(tmp_path: Path) -> None:
    (tmp_path / "stockmanager_backup_pg_20260102_030405.dump").write_bytes(b"x")
    (tmp_path / "stockmanager_backup_20260102_030405.db").write_bytes(b"x")  # SQLite : jamais listé ici.
    (tmp_path / "autre_fichier.dump").write_bytes(b"x")  # Hors motif StockManager : jamais listé.

    files = eng.list_backup_files(tmp_path)

    assert [f.name for f in files] == ["stockmanager_backup_pg_20260102_030405.dump"]


def test_apply_retention_keeps_only_the_most_recent(tmp_path: Path) -> None:
    import time

    for i in range(4):
        (tmp_path / f"stockmanager_backup_pg_2026010{i + 1}_030405.dump").write_bytes(b"x")
        time.sleep(0.01)

    deleted = eng.apply_retention(tmp_path, retention=2)

    assert len(deleted) == 2
    remaining = {f.name for f in eng.list_backup_files(tmp_path)}
    assert remaining == {"stockmanager_backup_pg_20260104_030405.dump", "stockmanager_backup_pg_20260103_030405.dump"}


def test_apply_retention_zero_or_negative_deletes_nothing(tmp_path: Path) -> None:
    (tmp_path / "stockmanager_backup_pg_20260101_030405.dump").write_bytes(b"x")
    assert eng.apply_retention(tmp_path, retention=0) == []
    assert eng.apply_retention(tmp_path, retention=-1) == []


# -- vérification d'une archive, sans serveur ---------------------------------------


def test_verify_backup_file_missing_file() -> None:
    result = eng.verify_backup_file(Path("/inexistant/fichier.dump"))
    assert result.valid is False
    assert "introuvable" in result.errors[0]


def test_verify_backup_file_rejects_corrupted_archive(tmp_path: Path) -> None:
    if shutil.which("pg_restore") is None:
        pytest.skip("pg_restore non installé dans cet environnement.")
    bad = tmp_path / "corrupted.dump"
    bad.write_bytes(b"ceci n'est pas une archive pg_dump" * 20)

    result = eng.verify_backup_file(bad)

    assert result.valid is False
    assert result.integrity_ok is False


# -- sauvegarde, vérification, restauration réelles (serveur PostgreSQL) -----------


def test_create_backup_file_produces_a_valid_verifiable_archive(pg_target_and_password, tmp_path: Path) -> None:
    target, password = pg_target_and_password
    destination = tmp_path / "backups"

    backup_path = eng.create_backup_file(target, password, destination)

    assert backup_path.exists()
    assert backup_path.suffix == ".dump"
    assert backup_path.stat().st_size > 0

    verification = eng.verify_backup_file(backup_path)
    assert verification.integrity_ok is True
    assert verification.alembic_version is not None


def test_create_backup_file_never_leaves_a_temp_file_on_success(pg_target_and_password, tmp_path: Path) -> None:
    target, password = pg_target_and_password
    destination = tmp_path / "backups"

    eng.create_backup_file(target, password, destination)

    assert list(destination.glob("*.tmp")) == []


def test_create_backup_file_wrong_password_raises_and_leaves_no_temp_file(
    pg_target_and_password, tmp_path: Path
) -> None:
    target, _ = pg_target_and_password
    destination = tmp_path / "backups"

    with pytest.raises(eng.PostgreSQLBackupError):
        eng.create_backup_file(target, "mot-de-passe-definitivement-incorrect", destination)

    assert list(destination.glob("*")) == [] or list(destination.glob("*.tmp")) == []


def test_get_live_alembic_version_matches_embedded_version_after_backup(
    pg_target_and_password, tmp_path: Path
) -> None:
    target, password = pg_target_and_password
    backup_path = eng.create_backup_file(target, password, tmp_path / "backups")

    live_version = eng.get_live_alembic_version(target, password)
    embedded_version = eng.get_embedded_alembic_version(backup_path)

    assert live_version is not None
    assert live_version == embedded_version


def test_get_live_alembic_version_returns_none_on_bad_password(pg_target_and_password) -> None:
    target, _ = pg_target_and_password
    assert eng.get_live_alembic_version(target, "mot-de-passe-incorrect") is None


def test_restore_round_trip_recovers_pre_backup_state(pg_target_and_password, tmp_path: Path) -> None:
    """Validation réelle exigée par le mandat (§E.2.4) : pas seulement la
    création d'une archive, mais une restauration réelle comparée à des
    données représentatives avant/après."""
    target, password = pg_target_and_password
    table = _scratch_table_name()

    def connect():
        return psycopg.connect(
            host=target.host, port=target.port, dbname=target.database,
            user=target.username, password=password,
        )

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE TABLE {table} (id serial PRIMARY KEY, label text)")
            cur.execute(f"INSERT INTO {table} (label) VALUES ('etat_sauvegarde')")
        conn.commit()

    try:
        backup_path = eng.create_backup_file(target, password, tmp_path / "backups")

        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE {table} SET label = 'etat_apres_derive'")
            conn.commit()

        eng.restore_database_from_backup(target, password, backup_path)

        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT label FROM {table}")
                rows = [r[0] for r in cur.fetchall()]
        assert rows == ["etat_sauvegarde"], "la restauration n'a pas recréé l'état sauvegardé"
    finally:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {table}")
            conn.commit()


def test_restore_of_corrupted_archive_never_touches_the_live_database(
    pg_target_and_password, tmp_path: Path
) -> None:
    """§E.2.3 : un échec de restauration ne doit jamais modifier la base
    active — vérifié ici avec une table/valeur témoin, pas seulement un
    code de retour."""
    target, password = pg_target_and_password
    table = _scratch_table_name()

    def connect():
        return psycopg.connect(
            host=target.host, port=target.port, dbname=target.database,
            user=target.username, password=password,
        )

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE TABLE {table} (id serial PRIMARY KEY, label text)")
            cur.execute(f"INSERT INTO {table} (label) VALUES ('ne_doit_jamais_changer')")
        conn.commit()

    bad_archive = tmp_path / "corrupted.dump"
    bad_archive.write_bytes(b"pas une vraie archive pg_dump" * 50)

    try:
        with pytest.raises(eng.PostgreSQLBackupError):
            eng.restore_database_from_backup(target, password, bad_archive)

        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT label FROM {table}")
                rows = [r[0] for r in cur.fetchall()]
        assert rows == ["ne_doit_jamais_changer"]
    finally:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {table}")
            conn.commit()


# -- diagnostic : stderr journalisé, jamais le mot de passe (Lot E.7, §E.7.1) -------

_DISTINCTIVE_FAKE_PASSWORD = "MOT-DE-PASSE-DE-TEST-JAMAIS-REEL-1234567890"

_ENGINE_LOGGER_NAME = "stockmanager.services.backups.postgresql"


@contextlib.contextmanager
def _capture_engine_error_logs(caplog: pytest.LogCaptureFixture) -> Iterator[None]:
    """``caplog`` attache son propre handler au logger racine (``""``) et
    s'appuie sur la propagation pour l'atteindre. Or
    ``app.utils.logging_config.setup_logging`` positionne délibérément,
    une seule fois par processus, ``logging.getLogger("stockmanager")
    .propagate = False`` (pour éviter une double sortie console/fichier) —
    un comportement préexistant, sans lien avec le Lot E, qui rend
    ``caplog.at_level(...)`` muet dès qu'un autre test de la suite complète
    a déjà appelé ``setup_logging`` avant celui-ci (constaté lors de
    l'exécution de la suite complète du Lot E.7, jamais en exécution
    isolée de ce seul fichier). Attacher le handler de ``caplog``
    directement au logger de ce module, plutôt que de compter sur la
    propagation jusqu'à la racine, rend la capture fiable dans les deux
    cas."""
    target_logger = logging.getLogger(_ENGINE_LOGGER_NAME)
    target_logger.addHandler(caplog.handler)
    previous_level = target_logger.level
    target_logger.setLevel(logging.ERROR)
    try:
        yield
    finally:
        target_logger.removeHandler(caplog.handler)
        target_logger.setLevel(previous_level)


def test_failed_backup_logs_technical_stderr_detail(
    pg_target_and_password, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """§E.7.1 : corrige le défaut relevé par l'audit — stderr doit
    désormais apparaître dans le journal applicatif lors d'un échec réel,
    pas seulement un code de retour nu."""
    target, _ = pg_target_and_password
    with _capture_engine_error_logs(caplog):
        with pytest.raises(eng.PostgreSQLBackupError):
            eng.create_backup_file(target, _DISTINCTIVE_FAKE_PASSWORD, tmp_path / "backups")

    logged_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "pg_dump a échoué" in logged_text
    # Le détail technique réel de pg_dump (ex. « password authentication
    # failed ») doit être présent — pas seulement un code de retour.
    assert "password" in logged_text.lower() or "authentification" in logged_text.lower()


def test_failed_backup_never_logs_the_password(
    pg_target_and_password, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    target, _ = pg_target_and_password
    with _capture_engine_error_logs(caplog):
        with pytest.raises(eng.PostgreSQLBackupError) as excinfo:
            eng.create_backup_file(target, _DISTINCTIVE_FAKE_PASSWORD, tmp_path / "backups")

    logged_text = "\n".join(record.getMessage() for record in caplog.records)
    assert _DISTINCTIVE_FAKE_PASSWORD not in logged_text
    assert _DISTINCTIVE_FAKE_PASSWORD not in str(excinfo.value)


def test_failed_restore_logs_technical_stderr_and_never_the_password(
    pg_target_and_password, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    target, password = pg_target_and_password
    backup_path = eng.create_backup_file(target, password, tmp_path / "backups")

    with _capture_engine_error_logs(caplog):
        with pytest.raises(eng.PostgreSQLBackupError) as excinfo:
            eng.restore_database_from_backup(target, _DISTINCTIVE_FAKE_PASSWORD, backup_path)

    logged_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "pg_restore a échoué" in logged_text
    assert _DISTINCTIVE_FAKE_PASSWORD not in logged_text
    assert _DISTINCTIVE_FAKE_PASSWORD not in str(excinfo.value)


def test_user_facing_exception_message_stays_generic_without_raw_stderr(
    pg_target_and_password, tmp_path: Path
) -> None:
    """Le message remonté à l'appelant (donc potentiellement affiché à
    l'utilisateur) ne doit jamais porter le texte brut de stderr — seul le
    journal applicatif (voir les tests ci-dessus) le reçoit."""
    target, _ = pg_target_and_password
    with pytest.raises(eng.PostgreSQLBackupError) as excinfo:
        eng.create_backup_file(target, _DISTINCTIVE_FAKE_PASSWORD, tmp_path / "backups")

    message = str(excinfo.value)
    assert "FATAL" not in message
    assert "authentication" not in message.lower()


# -- diagnostic de compatibilité de version, sans comparaison fragile (§E.7.3) ------


def test_logged_failure_includes_local_tool_version_for_correlation(
    pg_target_and_password, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    target, _ = pg_target_and_password
    with _capture_engine_error_logs(caplog):
        with pytest.raises(eng.PostgreSQLBackupError):
            eng.create_backup_file(target, _DISTINCTIVE_FAKE_PASSWORD, tmp_path / "backups")

    logged_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "version locale" in logged_text
    assert "PostgreSQL" in logged_text  # présent dans la sortie de "pg_dump --version"


def test_local_tool_version_handles_missing_tool_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(eng.shutil, "which", lambda name: None)
    assert eng._local_tool_version("pg_dump_introuvable_xyz") == "(version locale indisponible)"

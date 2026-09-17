import sqlite3
import time
from pathlib import Path

import pytest

from app.config.settings import Settings
from app.services.backups import backup_engine


def _make_source_db(path: Path) -> None:
    """Petite base SQLite autonome (pas de dépendance à l'application) pour
    tester la mécanique de sauvegarde/restauration indépendamment du schéma
    complet — utilisée pour les scénarios génériques (rotation, collision,
    fichier introuvable, ...)."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, valeur TEXT)")
    conn.execute("INSERT INTO demo (valeur) VALUES ('a')")
    conn.commit()
    conn.close()


# -- création de sauvegarde -------------------------------------------------------


def test_create_backup_file_produces_readable_sqlite_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    _make_source_db(source)
    destination_dir = tmp_path / "backups"

    backup_path = backup_engine.create_backup_file(source, destination_dir)

    assert backup_path.exists()
    conn = sqlite3.connect(str(backup_path))
    rows = conn.execute("SELECT valeur FROM demo").fetchall()
    conn.close()
    assert rows == [("a",)]


def test_create_backup_file_avoids_name_collision(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    _make_source_db(source)
    destination_dir = tmp_path / "backups"

    from datetime import datetime

    fixed_time = datetime(2026, 1, 1, 2, 0, 0)
    first = backup_engine.create_backup_file(source, destination_dir, when=fixed_time)
    second = backup_engine.create_backup_file(source, destination_dir, when=fixed_time)

    assert first != second
    assert first.exists()
    assert second.exists()


def test_create_backup_file_works_with_concurrent_write(tmp_path: Path) -> None:
    """La sauvegarde doit fonctionner même si une transaction est en cours
    sur la source (§3)."""
    source = tmp_path / "source.db"
    _make_source_db(source)
    destination_dir = tmp_path / "backups"

    writer_conn = sqlite3.connect(str(source))
    writer_conn.execute("BEGIN")
    writer_conn.execute("INSERT INTO demo (valeur) VALUES ('en cours')")
    # Transaction non validée : la sauvegarde doit tout de même réussir et
    # rester cohérente (l'API de sauvegarde SQLite gère cette situation).
    try:
        backup_path = backup_engine.create_backup_file(source, destination_dir)
        assert backup_path.exists()
        verification = backup_engine.verify_backup_file(backup_path)
        assert verification.integrity_ok
    finally:
        writer_conn.rollback()
        writer_conn.close()


def test_create_backup_file_raises_on_unwritable_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    _make_source_db(source)
    # Un fichier, pas un dossier : mkdir(parents=True, exist_ok=True) échoue.
    blocked = tmp_path / "not_a_dir"
    blocked.write_text("obstacle")

    with pytest.raises(OSError):
        backup_engine.create_backup_file(source, blocked)


# -- vérification -----------------------------------------------------------------


def test_verify_backup_file_valid_stockmanager_database(initialized_db: Settings, tmp_path: Path) -> None:
    backup_path = backup_engine.create_backup_file(initialized_db.db_path, tmp_path / "backups")

    verification = backup_engine.verify_backup_file(backup_path)

    assert verification.valid is True
    assert verification.integrity_ok is True
    assert verification.tables_ok is True
    assert verification.alembic_version is not None


def test_verify_backup_file_missing_file(tmp_path: Path) -> None:
    verification = backup_engine.verify_backup_file(tmp_path / "does_not_exist.db")

    assert verification.valid is False
    assert verification.errors


def test_verify_backup_file_not_a_sqlite_database(tmp_path: Path) -> None:
    fake = tmp_path / "fake.db"
    fake.write_bytes(b"pas une base sqlite")

    verification = backup_engine.verify_backup_file(fake)

    assert verification.valid is False


def test_verify_backup_file_missing_expected_tables(tmp_path: Path) -> None:
    incomplete = tmp_path / "incomplete.db"
    conn = sqlite3.connect(str(incomplete))
    conn.execute("CREATE TABLE autre_chose (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    verification = backup_engine.verify_backup_file(incomplete)

    assert verification.valid is False
    assert verification.tables_ok is False


def test_verify_backup_file_does_not_write_to_the_file(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    _make_source_db(source)
    backup_path = backup_engine.create_backup_file(source, tmp_path / "backups")
    mtime_before = backup_path.stat().st_mtime

    time.sleep(0.05)
    backup_engine.verify_backup_file(backup_path)

    assert backup_path.stat().st_mtime == mtime_before


# -- rotation / rétention -----------------------------------------------------------


def test_apply_retention_keeps_only_configured_count(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    _make_source_db(source)
    destination_dir = tmp_path / "backups"

    from datetime import datetime, timedelta

    base = datetime(2026, 1, 1, 2, 0, 0)
    for i in range(5):
        backup_engine.create_backup_file(source, destination_dir, when=base + timedelta(seconds=i))

    deleted = backup_engine.apply_retention(destination_dir, retention=2)

    remaining = backup_engine.list_backup_files(destination_dir)
    assert len(remaining) == 2
    assert len(deleted) == 3


def test_apply_retention_keeps_most_recent(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    _make_source_db(source)
    destination_dir = tmp_path / "backups"

    from datetime import datetime, timedelta

    base = datetime(2026, 1, 1, 2, 0, 0)
    oldest = backup_engine.create_backup_file(source, destination_dir, when=base)
    backup_engine.create_backup_file(source, destination_dir, when=base + timedelta(seconds=1))
    newest = backup_engine.create_backup_file(source, destination_dir, when=base + timedelta(seconds=2))

    backup_engine.apply_retention(destination_dir, retention=2)

    remaining_names = {p.name for p in backup_engine.list_backup_files(destination_dir)}
    assert newest.name in remaining_names
    assert oldest.name not in remaining_names


def test_apply_retention_only_deletes_stockmanager_backups(tmp_path: Path) -> None:
    """Ne supprime jamais un fichier ne correspondant pas exactement au
    motif de nommage StockManager (§6) — même un ``.db`` quelconque présent
    dans le même dossier doit être préservé."""
    source = tmp_path / "source.db"
    _make_source_db(source)
    destination_dir = tmp_path / "backups"
    destination_dir.mkdir()

    foreign_file = destination_dir / "un_autre_fichier.db"
    foreign_file.write_bytes(b"donnees etrangeres")
    important_txt = destination_dir / "notes.txt"
    important_txt.write_text("a ne pas toucher")

    from datetime import datetime, timedelta

    base = datetime(2026, 1, 1, 2, 0, 0)
    for i in range(3):
        backup_engine.create_backup_file(source, destination_dir, when=base + timedelta(seconds=i))

    backup_engine.apply_retention(destination_dir, retention=1)

    assert foreign_file.exists()
    assert important_txt.exists()


def test_apply_retention_never_touches_prerestore_backups(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    _make_source_db(source)
    destination_dir = tmp_path / "backups"

    prerestore = backup_engine.create_backup_file(source, destination_dir, prefix=backup_engine.PRERESTORE_PREFIX)
    backup_engine.create_backup_file(source, destination_dir)
    backup_engine.create_backup_file(source, destination_dir)

    backup_engine.apply_retention(destination_dir, retention=0)  # rotation normale, préfixe stockmanager_backup

    assert prerestore.exists()


def test_apply_retention_with_zero_or_negative_deletes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    _make_source_db(source)
    destination_dir = tmp_path / "backups"
    backup_engine.create_backup_file(source, destination_dir)

    deleted = backup_engine.apply_retention(destination_dir, retention=0)

    assert deleted == []
    assert len(backup_engine.list_backup_files(destination_dir)) == 1


def test_list_backup_files_returns_empty_for_missing_directory(tmp_path: Path) -> None:
    assert backup_engine.list_backup_files(tmp_path / "does_not_exist") == []


# -- restauration (mécanique) ---------------------------------------------------------


def test_restore_database_from_backup_replaces_content(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    _make_source_db(source)
    backup_path = backup_engine.create_backup_file(source, tmp_path / "backups")

    # Modifie la source après la sauvegarde.
    conn = sqlite3.connect(str(source))
    conn.execute("INSERT INTO demo (valeur) VALUES ('ajoute apres sauvegarde')")
    conn.commit()
    conn.close()

    target = tmp_path / "restored.db"
    _make_source_db(target)  # base cible préexistante, avec un contenu différent
    backup_engine.restore_database_from_backup(backup_path, target)

    conn = sqlite3.connect(str(target))
    rows = conn.execute("SELECT valeur FROM demo").fetchall()
    conn.close()
    assert rows == [("a",)]  # état au moment de la sauvegarde, pas l'ajout ultérieur

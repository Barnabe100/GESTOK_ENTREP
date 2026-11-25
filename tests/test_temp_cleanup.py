"""Vérifie app.services.backups.temp_cleanup — mission corrective
« Fiabilisation du module de sauvegarde », §3.13 (nettoyage prudent des
fichiers temporaires orphelins)."""
import os
import time

from app.services.backups.temp_cleanup import cleanup_orphaned_temp_files


def _touch_with_age(path, age_seconds: float) -> None:
    path.write_bytes(b"contenu temporaire")
    old_time = time.time() - age_seconds
    os.utime(path, (old_time, old_time))


def test_removes_an_old_orphaned_temp_file(tmp_path) -> None:
    orphan = tmp_path / ".stockmanager_backup_20260101_020000.db_abcdef.creating.tmp"
    _touch_with_age(orphan, age_seconds=7200)

    removed = cleanup_orphaned_temp_files(tmp_path, min_age_seconds=3600)

    assert removed == [orphan]
    assert not orphan.exists()


def test_never_removes_a_recent_temp_file(tmp_path) -> None:
    """Une opération légitime encore en cours (ou tout juste terminée)
    doit toujours survivre — jamais une suppression trop agressive."""
    recent = tmp_path / ".stockmanager_backup_20260101_020000.db_abcdef.creating.tmp"
    _touch_with_age(recent, age_seconds=5)

    removed = cleanup_orphaned_temp_files(tmp_path, min_age_seconds=3600)

    assert removed == []
    assert recent.exists()


def test_never_removes_a_regular_backup_file(tmp_path) -> None:
    """Un fichier de sauvegarde réel (jamais caché, jamais ``.tmp``) ne
    doit jamais être considéré comme un orphelin, quel que soit son
    âge."""
    real_backup = tmp_path / "stockmanager_backup_20200101_020000.db"
    _touch_with_age(real_backup, age_seconds=999999)

    removed = cleanup_orphaned_temp_files(tmp_path, min_age_seconds=3600)

    assert removed == []
    assert real_backup.exists()


def test_never_removes_a_hidden_file_that_does_not_end_in_tmp(tmp_path) -> None:
    other = tmp_path / ".gitkeep"
    _touch_with_age(other, age_seconds=999999)

    removed = cleanup_orphaned_temp_files(tmp_path, min_age_seconds=3600)

    assert removed == []
    assert other.exists()


def test_recognizes_every_known_temp_suffix(tmp_path) -> None:
    suffixes = [".creating.tmp", ".enc.tmp", ".dec.tmp", ".dump.tmp", ".tmp"]
    orphans = []
    for index, suffix in enumerate(suffixes):
        orphan = tmp_path / f".exemple_{index}{suffix}"
        _touch_with_age(orphan, age_seconds=7200)
        orphans.append(orphan)

    removed = cleanup_orphaned_temp_files(tmp_path, min_age_seconds=3600)

    assert set(removed) == set(orphans)
    assert all(not orphan.exists() for orphan in orphans)


def test_returns_empty_list_for_a_missing_directory(tmp_path) -> None:
    assert cleanup_orphaned_temp_files(tmp_path / "absent") == []


def test_never_descends_into_subdirectories(tmp_path) -> None:
    subdir = tmp_path / "sous_dossier"
    subdir.mkdir()
    nested_orphan = subdir / ".exemple.tmp"
    _touch_with_age(nested_orphan, age_seconds=7200)

    removed = cleanup_orphaned_temp_files(tmp_path, min_age_seconds=3600)

    assert removed == []
    assert nested_orphan.exists()

import json

from app.services.backups import archive_manifest
from app.version import __version__


def _write_archive(tmp_path, content: bytes = b"donnees de sauvegarde") -> "Path":
    path = tmp_path / "stockmanager_backup_20260101_020000.db"
    path.write_bytes(content)
    return path


def test_manifest_path_appends_suffix_without_replacing_extension(tmp_path) -> None:
    archive = _write_archive(tmp_path)

    manifest_path = archive_manifest.manifest_path_for(archive)

    assert manifest_path.name == "stockmanager_backup_20260101_020000.db.manifest.json"


def test_compute_sha256_is_deterministic_and_content_sensitive(tmp_path) -> None:
    archive_a = _write_archive(tmp_path, b"contenu A")
    archive_b = tmp_path / "b.db"
    archive_b.write_bytes(b"contenu B")

    hash_a1 = archive_manifest.compute_sha256(archive_a)
    hash_a2 = archive_manifest.compute_sha256(archive_a)
    hash_b = archive_manifest.compute_sha256(archive_b)

    assert hash_a1 == hash_a2
    assert hash_a1 != hash_b
    assert len(hash_a1) == 64  # hex SHA-256


def test_build_manifest_captures_current_file_state(tmp_path) -> None:
    archive = _write_archive(tmp_path, b"x" * 1000)

    manifest = archive_manifest.build_manifest(
        archive, db_engine="sqlite", schema_version="abc123", backup_type=archive_manifest.BACKUP_TYPE_LOCAL,
    )

    assert manifest.format_version == archive_manifest.FORMAT_VERSION
    assert manifest.stockmanager_version == __version__
    assert manifest.db_engine == "sqlite"
    assert manifest.schema_version == "abc123"
    assert manifest.backup_type == archive_manifest.BACKUP_TYPE_LOCAL
    assert manifest.size_bytes == 1000
    assert manifest.sha256 == archive_manifest.compute_sha256(archive)
    assert manifest.encrypted is False


def test_write_then_read_manifest_round_trips(tmp_path) -> None:
    archive = _write_archive(tmp_path)

    written = archive_manifest.write_manifest_for(
        archive, db_engine="postgresql", schema_version="xyz789",
        backup_type=archive_manifest.BACKUP_TYPE_EXTERNAL, encrypted=True,
    )
    read_back = archive_manifest.read_manifest_for(archive)

    assert read_back == written
    assert archive_manifest.manifest_path_for(archive).is_file()


def test_delete_manifest_removes_sidecar_file(tmp_path) -> None:
    archive = _write_archive(tmp_path)
    archive_manifest.write_manifest_for(
        archive, db_engine="sqlite", schema_version=None, backup_type=archive_manifest.BACKUP_TYPE_LOCAL,
    )

    archive_manifest.delete_manifest_for(archive)

    assert not archive_manifest.manifest_path_for(archive).exists()


def test_delete_manifest_is_idempotent_when_absent(tmp_path) -> None:
    archive = _write_archive(tmp_path)

    archive_manifest.delete_manifest_for(archive)  # ne doit jamais lever


def test_read_manifest_returns_none_when_absent(tmp_path) -> None:
    archive = _write_archive(tmp_path)

    assert archive_manifest.read_manifest_for(archive) is None


def test_read_manifest_returns_none_on_corrupted_json(tmp_path) -> None:
    archive = _write_archive(tmp_path)
    archive_manifest.manifest_path_for(archive).write_text("{ceci n'est pas du json valide", encoding="utf-8")

    assert archive_manifest.read_manifest_for(archive) is None


def test_read_manifest_ignores_unknown_future_fields(tmp_path) -> None:
    """Compatibilité ascendante (§ docstring de module) : un manifeste
    produit par une version future portant un champ supplémentaire reste
    lisible, le champ inconnu étant simplement ignoré."""
    archive = _write_archive(tmp_path)
    manifest = archive_manifest.build_manifest(
        archive, db_engine="sqlite", schema_version=None, backup_type=archive_manifest.BACKUP_TYPE_LOCAL,
    )
    data = json.loads(manifest.to_json())
    data["champ_du_futur_inconnu"] = "valeur"
    archive_manifest.manifest_path_for(archive).write_text(json.dumps(data), encoding="utf-8")

    read_back = archive_manifest.read_manifest_for(archive)

    assert read_back is not None
    assert read_back.db_engine == "sqlite"


def test_verify_manifest_passes_when_file_unchanged(tmp_path) -> None:
    archive = _write_archive(tmp_path)
    archive_manifest.write_manifest_for(
        archive, db_engine="sqlite", schema_version=None, backup_type=archive_manifest.BACKUP_TYPE_LOCAL,
    )

    result = archive_manifest.verify_manifest_for(archive)

    assert result.present is True
    assert result.hash_matches is True
    assert result.errors == []


def test_verify_manifest_fails_when_file_modified_after_manifest(tmp_path) -> None:
    archive = _write_archive(tmp_path)
    archive_manifest.write_manifest_for(
        archive, db_engine="sqlite", schema_version=None, backup_type=archive_manifest.BACKUP_TYPE_LOCAL,
    )
    archive.write_bytes(b"contenu modifie apres coup")

    result = archive_manifest.verify_manifest_for(archive)

    assert result.present is True
    assert result.hash_matches is False
    assert result.errors


def test_verify_manifest_reports_absence_without_raising(tmp_path) -> None:
    archive = _write_archive(tmp_path)

    result = archive_manifest.verify_manifest_for(archive)

    assert result.present is False
    assert result.hash_matches is False
    assert result.errors


def test_verify_manifest_fails_when_archive_file_missing(tmp_path) -> None:
    archive = _write_archive(tmp_path)
    archive_manifest.write_manifest_for(
        archive, db_engine="sqlite", schema_version=None, backup_type=archive_manifest.BACKUP_TYPE_LOCAL,
    )
    archive.unlink()

    result = archive_manifest.verify_manifest_for(archive)

    assert result.present is True
    assert result.hash_matches is False
    assert result.errors

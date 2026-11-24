from app.services.backups import external_media


def test_create_marker_writes_a_readable_marker(tmp_path) -> None:
    drive = tmp_path / "drive"
    drive.mkdir()

    created = external_media.create_marker(drive, "Clé USB Jean")
    read_back = external_media.read_marker(drive)

    assert read_back == created
    assert created.label == "Clé USB Jean"
    assert created.marker_id  # UUID non vide


def test_read_marker_returns_none_when_absent(tmp_path) -> None:
    drive = tmp_path / "drive"
    drive.mkdir()

    assert external_media.read_marker(drive) is None


def test_read_marker_returns_none_on_corrupted_file(tmp_path) -> None:
    drive = tmp_path / "drive"
    drive.mkdir()
    marker_path = drive / external_media.MARKER_DIRNAME / external_media.MARKER_FILENAME
    marker_path.parent.mkdir(parents=True)
    marker_path.write_text("{pas du json valide", encoding="utf-8")

    assert external_media.read_marker(drive) is None


def test_create_marker_replaces_existing_marker(tmp_path) -> None:
    drive = tmp_path / "drive"
    drive.mkdir()
    first = external_media.create_marker(drive, "Ancien nom")

    second = external_media.create_marker(drive, "Nouveau nom")

    read_back = external_media.read_marker(drive)
    assert read_back == second
    assert read_back.marker_id != first.marker_id


def test_find_marker_drive_locates_the_matching_root_among_several(tmp_path) -> None:
    drive_a = tmp_path / "a"
    drive_a.mkdir()
    drive_b = tmp_path / "b"
    drive_b.mkdir()
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()

    external_media.create_marker(drive_a, "A")
    marker_b = external_media.create_marker(drive_b, "B")

    found = external_media.find_marker_drive(marker_b.marker_id, candidate_roots=[unrelated, drive_a, drive_b])

    assert found == drive_b


def test_find_marker_drive_returns_none_when_media_absent(tmp_path) -> None:
    drive = tmp_path / "drive"
    drive.mkdir()
    external_media.create_marker(drive, "Présent")

    found = external_media.find_marker_drive("un-identifiant-qui-nexiste-pas", candidate_roots=[drive])

    assert found is None


def test_find_marker_drive_with_no_candidate_roots_returns_none(tmp_path) -> None:
    assert external_media.find_marker_drive("peu-importe", candidate_roots=[]) is None


def test_is_media_accessible_reflects_find_marker_drive(tmp_path) -> None:
    drive = tmp_path / "drive"
    drive.mkdir()
    marker = external_media.create_marker(drive, "Présent")

    assert external_media.is_media_accessible(marker.marker_id, candidate_roots=[drive]) is True
    assert external_media.is_media_accessible("absent", candidate_roots=[drive]) is False


def test_list_candidate_drive_roots_returns_empty_list_outside_windows() -> None:
    """Sous Linux (environnement de ce test), aucune notion de lettre de
    lecteur — liste vide, jamais une exception."""
    import sys

    if sys.platform == "win32":
        return  # Comportement réel (énumération C:/.. Z:/) non testé ici, voir §8 du mandat.
    assert external_media.list_candidate_drive_roots() == []

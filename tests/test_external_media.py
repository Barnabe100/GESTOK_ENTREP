from pathlib import Path

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


# -- mission corrective §2.2/§3.1 : normalisation de la racine du lecteur ------


class TestNormalizeDriveRoot:
    def test_already_canonical_root_is_unchanged(self) -> None:
        assert external_media.normalize_drive_root("E:/") == Path("E:/")

    def test_drive_letter_without_trailing_slash_is_a_known_windows_trap(self) -> None:
        """``« E: »`` seul est, en pathlib/Windows, un chemin RELATIF à ce
        lecteur (jamais sa racine absolue) — cause racine confirmée du
        défaut diagnostiqué (succès de configuration puis échec immédiat
        du test d'accessibilité). La normalisation doit toujours produire
        la racine canonique, jamais laisser passer cette forme ambiguë."""
        assert external_media.normalize_drive_root("E:") == Path("E:/")

    def test_backslash_form_is_normalized(self) -> None:
        assert external_media.normalize_drive_root("e:\\") == Path("E:/")

    def test_subfolder_is_collapsed_to_the_drive_root(self) -> None:
        """Un sous-dossier sélectionné par erreur (l'ancien sélecteur de
        dossier générique, désormais remplacé — voir §2.4 du mandat) ne
        doit jamais produire un marqueur introuvable ensuite : toujours
        ramené à la racine du lecteur."""
        assert external_media.normalize_drive_root("E:/Mes Sauvegardes/USB") == Path("E:/")

    def test_lowercase_letter_is_uppercased(self) -> None:
        assert external_media.normalize_drive_root("f:/dossier") == Path("F:/")

    def test_path_without_a_drive_letter_is_returned_unchanged(self) -> None:
        """Un chemin POSIX (utilisé comme racine de test partout ailleurs
        dans cette suite, sur une plateforme sans notion de lettre de
        lecteur) n'est jamais rejeté — seule une forme ``lettre:`` est
        normalisée (voir la docstring de la fonction) ; juger qu'une
        racine donnée est une destination appropriée relève de
        :func:`external_media.list_drives_with_info`, pas de cette
        fonction."""
        assert external_media.normalize_drive_root("/home/user/support") == Path("/home/user/support")

    def test_unc_network_path_is_returned_unchanged(self) -> None:
        assert external_media.normalize_drive_root(r"\\serveur\partage") == Path(r"\\serveur\partage")


# -- mission corrective §2.2 : vérification d'accessibilité en écriture -------


def test_check_root_accessible_returns_none_for_a_writable_directory(tmp_path) -> None:
    drive = tmp_path / "drive"
    drive.mkdir()

    assert external_media.check_root_accessible(drive) is None


def test_check_root_accessible_reports_a_missing_root() -> None:
    message = external_media.check_root_accessible(Path("/chemin/qui/nexiste/pas"))

    assert message is not None
    assert "n'existe pas" in message


def test_check_root_accessible_never_leaves_its_probe_file_behind(tmp_path) -> None:
    drive = tmp_path / "drive"
    drive.mkdir()

    external_media.check_root_accessible(drive)

    assert list(drive.iterdir()) == []


def test_check_root_accessible_reports_a_support_refusing_writes(tmp_path, monkeypatch) -> None:
    """Support présent (lettre attribuée, dossier visible) mais refusant
    réellement l'écriture — carte mémoire protégée, disque en lecture
    seule, etc. (mission corrective, test-plan §5 : « support en lecture
    seule »). Simulé en forçant l'échec de la sonde d'écriture elle-même
    plutôt que via les bits de permission POSIX, qui ne bloqueraient pas
    un processus root (cas de cette suite de tests)."""
    drive = tmp_path / "drive"
    drive.mkdir()

    def _raise(*args, **kwargs):
        raise OSError("Lecteur en lecture seule (simulation)")

    monkeypatch.setattr(external_media.tempfile, "mkstemp", _raise)

    message = external_media.check_root_accessible(drive)

    assert message is not None
    assert "n'est pas accessible en écriture" in message


# -- mission corrective §2.2 : énumération des lecteurs appropriés -----------


class TestListDrivesWithInfo:
    """Mission corrective « Correction et validation du module de
    sauvegarde sous Windows », §2 : ne jamais filtrer exclusivement selon
    DRIVE_REMOVABLE (certains disques durs externes USB sont identifiés
    comme DRIVE_FIXED par Windows), mais toujours exclure le disque
    système et les destinations inappropriées (réseau, optique, RAM)."""

    def _resolvers(self, types: dict) -> dict:
        return {
            "drive_type_resolver": lambda root: types.get(str(root), "other"),
            "volume_label_resolver": lambda root: f"Volume {root}",
        }

    def test_includes_removable_drives(self, tmp_path) -> None:
        usb = tmp_path / "usb"
        usb.mkdir()

        infos = external_media.list_drives_with_info(
            candidate_roots=[usb], **self._resolvers({str(usb): "removable"}),
        )

        assert len(infos) == 1
        assert infos[0].drive_type == "removable"

    def test_includes_fixed_external_drives(self, tmp_path) -> None:
        """Un disque dur externe USB est très souvent rapporté par Windows
        comme DRIVE_FIXED, pas DRIVE_REMOVABLE — doit tout de même être
        proposé (mission corrective, §2)."""
        external_hdd = tmp_path / "external_hdd"
        external_hdd.mkdir()

        infos = external_media.list_drives_with_info(
            candidate_roots=[external_hdd], **self._resolvers({str(external_hdd): "fixed"}),
        )

        assert len(infos) == 1
        assert infos[0].drive_type == "fixed"

    def test_excludes_network_optical_and_ramdisk_drives(self, tmp_path) -> None:
        network = tmp_path / "network"
        network.mkdir()
        optical = tmp_path / "optical"
        optical.mkdir()
        ramdisk = tmp_path / "ramdisk"
        ramdisk.mkdir()

        infos = external_media.list_drives_with_info(
            candidate_roots=[network, optical, ramdisk],
            **self._resolvers({str(network): "remote", str(optical): "cdrom", str(ramdisk): "ramdisk"}),
        )

        assert infos == []

    def test_excludes_the_system_drive_by_letter(self, monkeypatch) -> None:
        from pathlib import Path

        monkeypatch.setenv("SystemDrive", "C:")
        c_drive = Path("C:/")
        d_drive = Path("D:/")

        infos = external_media.list_drives_with_info(
            candidate_roots=[c_drive, d_drive],
            **self._resolvers({"C:": "fixed", "D:": "fixed"}),
        )

        assert [info.root for info in infos] == [d_drive]

    def test_includes_marker_when_present(self, tmp_path) -> None:
        usb = tmp_path / "usb"
        usb.mkdir()
        marker = external_media.create_marker(usb, "Mon support")

        infos = external_media.list_drives_with_info(
            candidate_roots=[usb], **self._resolvers({str(usb): "removable"}),
        )

        assert infos[0].marker == marker

    def test_returns_empty_list_outside_windows_without_injected_roots(self) -> None:
        import sys

        if sys.platform == "win32":
            return
        assert external_media.list_drives_with_info() == []

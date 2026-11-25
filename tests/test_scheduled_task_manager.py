"""Tests unitaires de app.services.backups.scheduled_task_manager — logique
pure (validation, construction de la ligne de commande, analyse de sortie)
et refus explicite hors Windows. Aucun de ces tests n'invoque réellement
``schtasks.exe`` : voir tests/test_scheduled_task_manager_windows_integration.py
pour les tests nécessitant réellement Windows (§8 du mandat)."""
import sys

import pytest

from app.services.backups import scheduled_task_manager as stm
from app.utils.exceptions import UnsupportedPlatformError

_skip_on_windows = pytest.mark.skipif(
    sys.platform == "win32", reason="Ces tests vérifient spécifiquement le refus hors Windows."
)


@_skip_on_windows
def test_task_exists_refuses_outside_windows() -> None:
    with pytest.raises(UnsupportedPlatformError):
        stm.task_exists("StockManager - Sauvegarde")


@_skip_on_windows
def test_create_or_repair_task_refuses_outside_windows() -> None:
    with pytest.raises(UnsupportedPlatformError):
        stm.create_or_repair_task("StockManager - Sauvegarde", "C:/StockManager/StockManager.exe", [], "20:00")


@_skip_on_windows
def test_delete_task_refuses_outside_windows() -> None:
    with pytest.raises(UnsupportedPlatformError):
        stm.delete_task("StockManager - Sauvegarde")


@_skip_on_windows
def test_query_task_status_refuses_outside_windows() -> None:
    with pytest.raises(UnsupportedPlatformError):
        stm.query_task_status("StockManager - Sauvegarde")


class TestErrorTranslation:
    """§8 du mandat : la traduction d'un échec de ``schtasks.exe`` (code de
    retour non nul — ex. droits insuffisants, tâche verrouillée) en
    :class:`stm.ScheduledTaskError` est une logique pure, indépendante de
    Windows lui-même (``_run_schtasks`` est substitué par un résultat
    synthétique) — seule l'invocation réelle de ``schtasks.exe`` nécessite
    Windows (voir tests/test_scheduled_task_manager_windows_integration.py).
    ``sys.platform`` est forcé à ``"win32"`` ici uniquement pour franchir le
    garde ``_ensure_windows`` au tout début de chaque fonction, jamais pour
    simuler quoi que ce soit d'autre."""

    @pytest.fixture(autouse=True)
    def _force_windows_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(stm.sys, "platform", "win32")

    def test_create_or_repair_task_raises_on_permission_denied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        def _fake_run_schtasks(args):
            return subprocess.CompletedProcess(args, returncode=5, stdout="", stderr="Accès refusé.")

        monkeypatch.setattr(stm, "_run_schtasks", _fake_run_schtasks)

        with pytest.raises(stm.ScheduledTaskError):
            stm.create_or_repair_task("StockManager - Sauvegarde", "C:/StockManager/StockManager.exe", [], "20:00")

    def test_delete_task_raises_on_permission_denied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        def _fake_run_schtasks(args):
            if args[0] == "/query":
                return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(args, returncode=5, stdout="", stderr="Accès refusé.")

        monkeypatch.setattr(stm, "_run_schtasks", _fake_run_schtasks)

        with pytest.raises(stm.ScheduledTaskError):
            stm.delete_task("StockManager - Sauvegarde")

    def test_query_task_status_reports_absent_on_failure_rather_than_raising(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess

        def _fake_run_schtasks(args):
            return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="ERREUR : tâche introuvable.")

        monkeypatch.setattr(stm, "_run_schtasks", _fake_run_schtasks)

        status = stm.query_task_status("StockManager - Sauvegarde")

        assert status.exists is False


def test_run_schtasks_translates_missing_binary_to_scheduled_task_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_run_schtasks`` lui-même n'appelle jamais ``_ensure_windows`` (ce
    sont ses appelants qui le font) : testable sans forcer
    ``sys.platform``, y compris pour la branche d'erreur (binaire absent,
    ex. ``schtasks.exe`` manquant ou inaccessible)."""
    def _raise_missing_binary(*args, **kwargs):
        raise FileNotFoundError("schtasks introuvable")

    monkeypatch.setattr(stm.subprocess, "run", _raise_missing_binary)

    with pytest.raises(stm.ScheduledTaskError):
        stm._run_schtasks(["/query", "/tn", "StockManager - Sauvegarde"])


class TestValidateTimeOfDay:
    def test_accepts_valid_times(self) -> None:
        for valid in ("00:00", "09:30", "20:00", "23:59"):
            stm._validate_time_of_day(valid)  # ne doit jamais lever

    @pytest.mark.parametrize("invalid", ["24:00", "20:60", "8:00", "20:5", "20h00", "", "20:00:00"])
    def test_rejects_invalid_times(self, invalid: str) -> None:
        with pytest.raises(stm.ScheduledTaskError):
            stm._validate_time_of_day(invalid)


class TestBuildTaskRunValue:
    def test_quotes_executable_path(self) -> None:
        value = stm._build_task_run_value("C:/Program Files/StockManager/StockManager.exe", [])

        assert value == '"C:/Program Files/StockManager/StockManager.exe"'

    def test_appends_arguments_unquoted(self) -> None:
        value = stm._build_task_run_value("C:/StockManager/StockManager.exe", ["--run-backup-agent"])

        assert value == '"C:/StockManager/StockManager.exe" --run-backup-agent'

    def test_supports_multiple_arguments(self) -> None:
        value = stm._build_task_run_value("app.exe", ["--a", "--b"])

        assert value == '"app.exe" --a --b'


class TestParseSchtasksVerboseList:
    _SAMPLE_OUTPUT = (
        "Folder: \\\n"
        "HostName:                            DESKTOP-TEST\n"
        "TaskName:                             \\StockManager - Sauvegarde\n"
        "Next Run Time:                        24/11/2026 20:00:00\n"
        "Status:                                Ready\n"
        "Logon Mode:                           Interactive only\n"
        "Last Run Time:                        23/11/2026 20:00:03\n"
        "Last Result:                          0\n"
        "Author:                               DESKTOP-TEST\\user\n"
    )

    def test_extracts_known_fields(self) -> None:
        fields = stm._parse_schtasks_verbose_list(self._SAMPLE_OUTPUT)

        assert fields["status"] == "Ready"
        assert fields["last_run_time"] == "23/11/2026 20:00:03"
        assert fields["last_result"] == "0"
        assert fields["next_run_time"] == "24/11/2026 20:00:00"

    def test_ignores_unknown_fields(self) -> None:
        fields = stm._parse_schtasks_verbose_list(self._SAMPLE_OUTPUT)

        assert "author" not in fields
        assert "hostname" not in fields
        assert "logon_mode" not in fields

    def test_handles_empty_output(self) -> None:
        assert stm._parse_schtasks_verbose_list("") == {}

    def test_ignores_lines_without_colon(self) -> None:
        fields = stm._parse_schtasks_verbose_list("ligne sans deux-points\nStatus: Disabled")

        assert fields == {"status": "Disabled"}


class TestOnLogonSchedule:
    """Mission corrective « Fiabilisation du module de sauvegarde », §3.5 :
    déclencheur à l'ouverture de session, en complément du quotidien —
    jamais invoqué réellement sur schtasks.exe ici (voir
    test_scheduled_task_manager_windows_integration.py pour l'intégration
    Windows réelle), seulement la construction de la ligne de commande."""

    @pytest.fixture(autouse=True)
    def _force_windows_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(stm.sys, "platform", "win32")

    def test_onlogon_builds_the_right_schtasks_arguments(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = {}

        def _fake_run_schtasks(args):
            captured["args"] = args
            import subprocess
            return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(stm, "_run_schtasks", _fake_run_schtasks)

        stm.create_or_repair_task(
            "StockManager - Sauvegarde (ouverture de session)", "C:/StockManager/StockManager.exe", [],
            "20:00", schedule=stm.SCHEDULE_ONLOGON,
        )

        assert "/onlogon" not in captured["args"]  # schtasks attend "onlogon" sans slash après /sc
        assert captured["args"][captured["args"].index("/sc") + 1] == "onlogon"
        assert "/st" not in captured["args"]  # jamais transmis pour ce type de déclencheur

    def test_onlogon_never_validates_time_of_day(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Une heure invalide ne doit jamais faire échouer une tâche
        « onlogon », puisqu'elle n'est de toute façon jamais utilisée."""
        import subprocess

        monkeypatch.setattr(
            stm, "_run_schtasks",
            lambda args: subprocess.CompletedProcess(args, returncode=0, stdout="", stderr=""),
        )

        stm.create_or_repair_task(
            "StockManager - Sauvegarde (ouverture de session)", "C:/StockManager/StockManager.exe", [],
            "heure invalide", schedule=stm.SCHEDULE_ONLOGON,
        )  # ne doit jamais lever.

    def test_daily_schedule_still_requires_a_valid_time(self) -> None:
        with pytest.raises(stm.ScheduledTaskError):
            stm.create_or_repair_task(
                "StockManager - Sauvegarde", "C:/StockManager/StockManager.exe", [],
                "heure invalide", schedule=stm.SCHEDULE_DAILY,
            )

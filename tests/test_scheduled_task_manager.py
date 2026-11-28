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

    def test_create_or_repair_task_error_message_contains_the_real_windows_cause(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mission corrective « Correction et validation du module de
        sauvegarde sous Windows », §4.3 : jamais seulement « code 1 » —
        toujours le détail Windows réel (``stderr``), ici à l'utilisateur
        et pas seulement au journal (voir ``_sanitized_stderr_excerpt``)."""
        import subprocess

        monkeypatch.setattr(
            stm, "_run_schtasks",
            lambda args: subprocess.CompletedProcess(
                args, returncode=1, stdout="",
                stderr="ERROR: The filename, directory name, or volume label syntax is incorrect.",
            ),
        )

        with pytest.raises(stm.ScheduledTaskError, match="filename, directory name, or volume label"):
            stm.create_or_repair_task("StockManager - Sauvegarde", "C:/StockManager/StockManager.exe", [], "20:00")

    def test_create_or_repair_task_cleans_up_temp_xml_file_even_on_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pathlib import Path

        import subprocess

        captured_path = {}

        def _fake_run_schtasks(args):
            if args[0] == "/query":
                # Lecture préalable de l'état existant (avant toute
                # création/réparation, voir ``create_or_repair_task``) —
                # non pertinente pour ce test, simulée comme « absente ».
                return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="")
            captured_path["path"] = Path(args[args.index("/xml") + 1])
            assert captured_path["path"].exists()
            return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="Échec simulé.")

        monkeypatch.setattr(stm, "_run_schtasks", _fake_run_schtasks)

        with pytest.raises(stm.ScheduledTaskError):
            stm.create_or_repair_task("StockManager - Sauvegarde", "C:/StockManager/StockManager.exe", [], "20:00")

        assert not captured_path["path"].exists()

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


class TestBuildTaskXml:
    """Mission corrective « Correction et validation du module de
    sauvegarde sous Windows », §3.2 : la définition de tâche est désormais
    un document XML (``schtasks /create /xml``), jamais une valeur ``/tr``
    en ligne de commande — ``executable``/``arguments`` vivent dans des
    éléments XML distincts (``<Command>``/``<Arguments>``), jamais
    concaténés en une seule chaîne nécessitant des guillemets imbriqués
    (voir la docstring de module de ``scheduled_task_manager`` pour le
    défaut ainsi éliminé, confirmé par simulation de
    ``subprocess.list2cmdline`` lors du diagnostic)."""

    @staticmethod
    def _parse(xml_bytes: bytes):
        import xml.etree.ElementTree as ET

        return ET.fromstring(xml_bytes.decode("utf-16"))

    def test_is_encoded_as_utf16_with_declaration(self) -> None:
        xml_bytes = stm._build_task_xml(
            "C:/StockManager/StockManager.exe", ["--run-backup-agent"],
            schedule=stm.SCHEDULE_DAILY, time_of_day="20:00", user_id="TESTPC\\testuser",
            )

        assert xml_bytes.startswith(b"\xff\xfe")  # BOM UTF-16 LE
        assert "utf-16" in xml_bytes.decode("utf-16").splitlines()[0].lower()

    def test_command_and_arguments_are_never_concatenated_or_requoted(self) -> None:
        """Régression directe du défaut diagnostiqué : un exécutable dont
        le chemin contient un espace (ex. « Program Files ») ne doit
        jamais produire de guillemets échappés imbriqués — ``<Command>``
        contient le chemin tel quel, sans aucun guillemet ajouté."""
        xml_bytes = stm._build_task_xml(
            "C:/Program Files/StockManager/StockManager.exe", ["--run-backup-agent"],
            schedule=stm.SCHEDULE_DAILY, time_of_day="20:00", user_id="TESTPC\\testuser",
            )

        root = self._parse(xml_bytes)
        ns = {"t": stm._TASK_XML_NS}
        command = root.find(".//t:Actions/t:Exec/t:Command", ns)
        arguments = root.find(".//t:Actions/t:Exec/t:Arguments", ns)

        assert command.text == "C:/Program Files/StockManager/StockManager.exe"
        assert '"' not in command.text
        assert arguments.text == "--run-backup-agent"

    def test_daily_schedule_builds_a_calendar_trigger(self) -> None:
        xml_bytes = stm._build_task_xml(
            "C:/StockManager/StockManager.exe", ["--run-backup-agent"],
            schedule=stm.SCHEDULE_DAILY, time_of_day="20:00", user_id="TESTPC\\testuser",
            )

        root = self._parse(xml_bytes)
        ns = {"t": stm._TASK_XML_NS}
        trigger = root.find(".//t:Triggers/t:CalendarTrigger", ns)
        assert trigger is not None
        assert trigger.find("t:StartBoundary", ns).text.endswith("T20:00:00")
        assert trigger.find("t:ScheduleByDay/t:DaysInterval", ns).text == "1"
        assert root.find(".//t:Triggers/t:LogonTrigger", ns) is None

    def test_onlogon_schedule_builds_a_logon_trigger_without_time(self) -> None:
        xml_bytes = stm._build_task_xml(
            "C:/StockManager/StockManager.exe", ["--run-backup-agent"],
            schedule=stm.SCHEDULE_ONLOGON, time_of_day="heure ignorée pour ce déclencheur", user_id="TESTPC\\testuser",
            )

        root = self._parse(xml_bytes)
        ns = {"t": stm._TASK_XML_NS}
        assert root.find(".//t:Triggers/t:LogonTrigger", ns) is not None
        assert root.find(".//t:Triggers/t:CalendarTrigger", ns) is None

    def test_daily_schedule_still_validates_time_of_day(self) -> None:
        with pytest.raises(stm.ScheduledTaskError):
            stm._build_task_xml(
                "C:/StockManager/StockManager.exe", [], schedule=stm.SCHEDULE_DAILY, time_of_day="heure invalide", user_id="TESTPC\\testuser",
            )

    def test_principal_never_requests_elevation_or_stored_credentials(self) -> None:
        """§4 du mandat initial : jamais d'élévation, jamais
        d'identifiants stockés — ``InteractiveToken``/``LeastPrivilege``,
        jamais ``Password``/``S4U``/``HighestAvailable``."""
        xml_bytes = stm._build_task_xml(
            "C:/StockManager/StockManager.exe", [], schedule=stm.SCHEDULE_DAILY, time_of_day="20:00", user_id="TESTPC\\testuser",
            )

        root = self._parse(xml_bytes)
        ns = {"t": stm._TASK_XML_NS}
        principal = root.find(".//t:Principals/t:Principal", ns)
        assert principal.find("t:LogonType", ns).text == "InteractiveToken"
        assert principal.find("t:RunLevel", ns).text == "LeastPrivilege"

    def test_never_skips_backups_on_battery_power(self) -> None:
        """Un poste portable ne doit jamais sauter silencieusement sa
        sauvegarde planifiée simplement parce qu'il fonctionne sur
        batterie — contrairement au réglage par défaut de l'interface
        graphique du Planificateur de tâches."""
        xml_bytes = stm._build_task_xml(
            "C:/StockManager/StockManager.exe", [], schedule=stm.SCHEDULE_DAILY, time_of_day="20:00", user_id="TESTPC\\testuser",
            )

        root = self._parse(xml_bytes)
        ns = {"t": stm._TASK_XML_NS}
        settings = root.find(".//t:Settings", ns)
        assert settings.find("t:DisallowStartIfOnBatteries", ns).text == "false"
        assert settings.find("t:StopIfGoingOnBatteries", ns).text == "false"
        assert settings.find("t:StartWhenAvailable", ns).text == "true"
        assert settings.find("t:MultipleInstancesPolicy", ns).text == "IgnoreNew"


class TestBuildTaskXmlWeeklyAndMonthly:
    """Mission « Gestion complète de la planification des sauvegardes
    Windows », §3.1 : fréquences hebdomadaire (un ou plusieurs jours) et
    mensuelle (jour fixe ou dernier jour du mois)."""

    @staticmethod
    def _parse(xml_bytes: bytes):
        import xml.etree.ElementTree as ET

        return ET.fromstring(xml_bytes.decode("utf-16"))

    def test_weekly_schedule_builds_a_schedule_by_week_with_the_selected_days(self) -> None:
        xml_bytes = stm._build_task_xml(
            "C:/StockManager/StockManager.exe", [], schedule=stm.SCHEDULE_WEEKLY, time_of_day="20:00",
            user_id="TESTPC\\testuser", weekly_days=frozenset({0, 3}),  # lundi, jeudi
        )

        root = self._parse(xml_bytes)
        ns = {"t": stm._TASK_XML_NS}
        trigger = root.find(".//t:Triggers/t:CalendarTrigger", ns)
        schedule_by_week = trigger.find("t:ScheduleByWeek", ns)
        assert schedule_by_week is not None
        days = schedule_by_week.find("t:DaysOfWeek", ns)
        assert days.find("t:Monday", ns) is not None
        assert days.find("t:Thursday", ns) is not None
        assert days.find("t:Tuesday", ns) is None
        assert schedule_by_week.find("t:WeeksInterval", ns).text == "1"
        assert trigger.find("t:ScheduleByDay", ns) is None
        assert trigger.find("t:ScheduleByMonth", ns) is None

    def test_weekly_schedule_without_any_day_raises(self) -> None:
        with pytest.raises(stm.ScheduledTaskError):
            stm._build_task_xml(
                "C:/StockManager/StockManager.exe", [], schedule=stm.SCHEDULE_WEEKLY, time_of_day="20:00",
                user_id="TESTPC\\testuser", weekly_days=frozenset(),
            )

    def test_monthly_schedule_with_a_fixed_day_builds_days_of_month(self) -> None:
        xml_bytes = stm._build_task_xml(
            "C:/StockManager/StockManager.exe", [], schedule=stm.SCHEDULE_MONTHLY, time_of_day="20:00",
            user_id="TESTPC\\testuser", monthly_day=15,
        )

        root = self._parse(xml_bytes)
        ns = {"t": stm._TASK_XML_NS}
        trigger = root.find(".//t:Triggers/t:CalendarTrigger", ns)
        schedule_by_month = trigger.find("t:ScheduleByMonth", ns)
        assert schedule_by_month is not None
        assert schedule_by_month.find("t:DaysOfMonth/t:Day", ns).text == "15"
        assert schedule_by_month.find("t:RunOnLastDayOfMonth", ns) is None
        months = schedule_by_month.find("t:Months", ns)
        assert months.find("t:January", ns) is not None
        assert months.find("t:December", ns) is not None

    def test_monthly_schedule_with_last_day_builds_run_on_last_day_of_month(self) -> None:
        xml_bytes = stm._build_task_xml(
            "C:/StockManager/StockManager.exe", [], schedule=stm.SCHEDULE_MONTHLY, time_of_day="20:00",
            user_id="TESTPC\\testuser", monthly_last_day=True,
        )

        root = self._parse(xml_bytes)
        ns = {"t": stm._TASK_XML_NS}
        schedule_by_month = root.find(".//t:Triggers/t:CalendarTrigger/t:ScheduleByMonth", ns)
        assert schedule_by_month.find("t:RunOnLastDayOfMonth", ns).text == "true"
        assert schedule_by_month.find("t:DaysOfMonth", ns) is None

    def test_monthly_schedule_without_a_valid_day_or_last_day_raises(self) -> None:
        with pytest.raises(stm.ScheduledTaskError):
            stm._build_task_xml(
                "C:/StockManager/StockManager.exe", [], schedule=stm.SCHEDULE_MONTHLY, time_of_day="20:00",
                user_id="TESTPC\\testuser", monthly_day=None, monthly_last_day=False,
            )

    def test_monthly_schedule_rejects_a_day_outside_one_to_thirty_one(self) -> None:
        with pytest.raises(stm.ScheduledTaskError):
            stm._build_task_xml(
                "C:/StockManager/StockManager.exe", [], schedule=stm.SCHEDULE_MONTHLY, time_of_day="20:00",
                user_id="TESTPC\\testuser", monthly_day=32,
            )


class TestParseTaskDefinition:
    """Mission « Gestion complète de la planification des sauvegardes
    Windows », §6 : relecture structurée de la définition XML réellement
    enregistrée — pour l'affichage (section « Détails de la tâche
    planifiée Windows ») et pour la vérification post-création."""

    def test_returns_none_for_unparseable_text(self) -> None:
        assert stm.parse_task_definition("pas du xml valide <<<") is None

    def test_extracts_command_and_arguments(self) -> None:
        xml_text = (
            f'<Task xmlns="{stm._TASK_XML_NS}"><Actions><Exec>'
            f"<Command>C:/StockManager/StockManager.exe</Command>"
            f"<Arguments>--run-backup-agent</Arguments></Exec></Actions></Task>"
        )

        definition = stm.parse_task_definition(xml_text)

        assert definition.command == "C:/StockManager/StockManager.exe"
        assert definition.arguments == "--run-backup-agent"

    def test_extracts_user_id_from_principal(self) -> None:
        xml_text = (
            f'<Task xmlns="{stm._TASK_XML_NS}"><Principals><Principal id="Author">'
            f"<UserId>DESKTOP-TEST\\jdupont</UserId></Principal></Principals></Task>"
        )

        definition = stm.parse_task_definition(xml_text)

        assert definition.user_id == "DESKTOP-TEST\\jdupont"

    def test_recognizes_onlogon_schedule_and_prefers_trigger_user_id(self) -> None:
        xml_text = (
            f'<Task xmlns="{stm._TASK_XML_NS}"><Principals><Principal id="Author">'
            f"<UserId>DESKTOP-TEST\\principal</UserId></Principal></Principals>"
            f"<Triggers><LogonTrigger><UserId>DESKTOP-TEST\\trigger</UserId></LogonTrigger></Triggers></Task>"
        )

        definition = stm.parse_task_definition(xml_text)

        assert definition.schedule_kind == stm.SCHEDULE_ONLOGON
        assert definition.user_id == "DESKTOP-TEST\\trigger"

    def test_recognizes_daily_schedule_and_extracts_time(self) -> None:
        xml_text = (
            f'<Task xmlns="{stm._TASK_XML_NS}"><Triggers><CalendarTrigger>'
            f"<StartBoundary>2024-01-01T20:00:00</StartBoundary>"
            f"<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>"
            f"</CalendarTrigger></Triggers></Task>"
        )

        definition = stm.parse_task_definition(xml_text)

        assert definition.schedule_kind == stm.SCHEDULE_DAILY
        assert definition.time_of_day == "20:00"

    def test_recognizes_weekly_schedule_and_extracts_days(self) -> None:
        xml_text = (
            f'<Task xmlns="{stm._TASK_XML_NS}"><Triggers><CalendarTrigger>'
            f"<StartBoundary>2024-01-01T20:00:00</StartBoundary>"
            f"<ScheduleByWeek><WeeksInterval>1</WeeksInterval>"
            f"<DaysOfWeek><Monday/><Thursday/></DaysOfWeek></ScheduleByWeek>"
            f"</CalendarTrigger></Triggers></Task>"
        )

        definition = stm.parse_task_definition(xml_text)

        assert definition.schedule_kind == stm.SCHEDULE_WEEKLY
        assert definition.weekly_days == frozenset({0, 3})

    def test_recognizes_monthly_schedule_with_fixed_day(self) -> None:
        xml_text = (
            f'<Task xmlns="{stm._TASK_XML_NS}"><Triggers><CalendarTrigger>'
            f"<StartBoundary>2024-01-01T20:00:00</StartBoundary>"
            f"<ScheduleByMonth><DaysOfMonth><Day>15</Day></DaysOfMonth></ScheduleByMonth>"
            f"</CalendarTrigger></Triggers></Task>"
        )

        definition = stm.parse_task_definition(xml_text)

        assert definition.schedule_kind == stm.SCHEDULE_MONTHLY
        assert definition.monthly_day == 15
        assert definition.monthly_last_day is False

    def test_recognizes_monthly_schedule_with_last_day(self) -> None:
        xml_text = (
            f'<Task xmlns="{stm._TASK_XML_NS}"><Triggers><CalendarTrigger>'
            f"<StartBoundary>2024-01-01T20:00:00</StartBoundary>"
            f"<ScheduleByMonth><RunOnLastDayOfMonth>true</RunOnLastDayOfMonth></ScheduleByMonth>"
            f"</CalendarTrigger></Triggers></Task>"
        )

        definition = stm.parse_task_definition(xml_text)

        assert definition.monthly_last_day is True
        assert definition.monthly_day is None


class TestQueryTaskDefinition:
    """Mission « Gestion complète de la planification des sauvegardes
    Windows », §6 : enveloppe publique autour de la relecture XML, pour
    l'affichage (``ExternalBackupService.scheduled_task_details``)."""

    @pytest.fixture(autouse=True)
    def _force_windows_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(stm.sys, "platform", "win32")

    def test_returns_none_when_schtasks_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        monkeypatch.setattr(
            stm, "_run_schtasks",
            lambda args: subprocess.CompletedProcess(args, returncode=1, stdout="", stderr=""),
        )

        assert stm.query_task_definition("StockManager - Sauvegarde") is None

    def test_returns_the_parsed_definition_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        xml_text = (
            f'<Task xmlns="{stm._TASK_XML_NS}"><Actions><Exec>'
            f"<Command>C:/StockManager/StockManager.exe</Command></Exec></Actions></Task>"
        )
        monkeypatch.setattr(
            stm, "_run_schtasks",
            lambda args: subprocess.CompletedProcess(args, returncode=0, stdout=xml_text, stderr=""),
        )

        definition = stm.query_task_definition("StockManager - Sauvegarde")

        assert definition is not None
        assert definition.command == "C:/StockManager/StockManager.exe"


class TestResolveCurrentUserId:
    def test_delegates_to_the_default_resolver(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("USERDOMAIN", "DESKTOP-TEST")
        monkeypatch.setenv("USERNAME", "jdupont")

        assert stm.resolve_current_user_id() == "DESKTOP-TEST\\jdupont"


class TestVerifyTaskRegisteredWeeklyAndMonthly:
    @pytest.fixture(autouse=True)
    def _force_windows_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(stm.sys, "platform", "win32")

    def test_raises_when_registered_weekly_days_differ(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        xml_wrong_days = (
            f'<Task xmlns="{stm._TASK_XML_NS}"><Triggers><CalendarTrigger>'
            f"<ScheduleByWeek><DaysOfWeek><Tuesday/></DaysOfWeek></ScheduleByWeek>"
            f"</CalendarTrigger></Triggers><Actions><Exec>"
            f"<Command>C:/StockManager/StockManager.exe</Command></Exec></Actions></Task>"
        )

        def _fake_run_schtasks(args):
            if "/xml" in args:
                return subprocess.CompletedProcess(args, returncode=0, stdout=xml_wrong_days, stderr="")
            return subprocess.CompletedProcess(args, returncode=0, stdout="Status: Ready", stderr="")

        monkeypatch.setattr(stm, "_run_schtasks", _fake_run_schtasks)

        with pytest.raises(stm.ScheduledTaskError, match="jours de la semaine"):
            stm._verify_task_registered(
                "StockManager - Sauvegarde", executable="C:/StockManager/StockManager.exe",
                schedule=stm.SCHEDULE_WEEKLY, weekly_days=frozenset({0, 3}),
            )

    def test_raises_when_registered_monthly_day_differs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        xml_wrong_day = (
            f'<Task xmlns="{stm._TASK_XML_NS}"><Triggers><CalendarTrigger>'
            f"<ScheduleByMonth><DaysOfMonth><Day>1</Day></DaysOfMonth></ScheduleByMonth>"
            f"</CalendarTrigger></Triggers><Actions><Exec>"
            f"<Command>C:/StockManager/StockManager.exe</Command></Exec></Actions></Task>"
        )

        def _fake_run_schtasks(args):
            if "/xml" in args:
                return subprocess.CompletedProcess(args, returncode=0, stdout=xml_wrong_day, stderr="")
            return subprocess.CompletedProcess(args, returncode=0, stdout="Status: Ready", stderr="")

        monkeypatch.setattr(stm, "_run_schtasks", _fake_run_schtasks)

        with pytest.raises(stm.ScheduledTaskError, match="jour du mois"):
            stm._verify_task_registered(
                "StockManager - Sauvegarde", executable="C:/StockManager/StockManager.exe",
                schedule=stm.SCHEDULE_MONTHLY, monthly_day=15,
            )

    def test_raises_when_last_day_setting_differs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        xml_not_last_day = (
            f'<Task xmlns="{stm._TASK_XML_NS}"><Triggers><CalendarTrigger>'
            f"<ScheduleByMonth><DaysOfMonth><Day>15</Day></DaysOfMonth></ScheduleByMonth>"
            f"</CalendarTrigger></Triggers><Actions><Exec>"
            f"<Command>C:/StockManager/StockManager.exe</Command></Exec></Actions></Task>"
        )

        def _fake_run_schtasks(args):
            if "/xml" in args:
                return subprocess.CompletedProcess(args, returncode=0, stdout=xml_not_last_day, stderr="")
            return subprocess.CompletedProcess(args, returncode=0, stdout="Status: Ready", stderr="")

        monkeypatch.setattr(stm, "_run_schtasks", _fake_run_schtasks)

        with pytest.raises(stm.ScheduledTaskError, match="dernier jour"):
            stm._verify_task_registered(
                "StockManager - Sauvegarde", executable="C:/StockManager/StockManager.exe",
                schedule=stm.SCHEDULE_MONTHLY, monthly_last_day=True,
            )

    def test_passes_when_weekly_days_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        xml_matching = (
            f'<Task xmlns="{stm._TASK_XML_NS}"><Triggers><CalendarTrigger>'
            f"<ScheduleByWeek><DaysOfWeek><Monday/><Thursday/></DaysOfWeek></ScheduleByWeek>"
            f"</CalendarTrigger></Triggers><Actions><Exec>"
            f"<Command>C:/StockManager/StockManager.exe</Command></Exec></Actions></Task>"
        )

        def _fake_run_schtasks(args):
            if "/xml" in args:
                return subprocess.CompletedProcess(args, returncode=0, stdout=xml_matching, stderr="")
            return subprocess.CompletedProcess(args, returncode=0, stdout="Status: Ready", stderr="")

        monkeypatch.setattr(stm, "_run_schtasks", _fake_run_schtasks)

        stm._verify_task_registered(
            "StockManager - Sauvegarde", executable="C:/StockManager/StockManager.exe",
            schedule=stm.SCHEDULE_WEEKLY, weekly_days=frozenset({0, 3}),
        )  # ne doit jamais lever.


class TestUserIdInTaskXml:
    """Mission corrective « Erreur Accès refusé de la tâche planifiée
    Windows » : cause racine identifiée — un ``<LogonTrigger>`` sans
    ``<UserId>`` surveille l'ouverture de session de n'importe quel
    utilisateur du poste, une capacité réservée à un compte administrateur
    (voir la docstring de module). Le scoper explicitement à l'utilisateur
    courant élimine le refus d'accès pour un compte standard."""

    @staticmethod
    def _parse(xml_bytes: bytes):
        import xml.etree.ElementTree as ET

        return ET.fromstring(xml_bytes.decode("utf-16"))

    def test_principal_carries_the_explicit_user_id(self) -> None:
        xml_bytes = stm._build_task_xml(
            "C:/StockManager/StockManager.exe", [], schedule=stm.SCHEDULE_DAILY, time_of_day="20:00",
            user_id="DESKTOP-TEST\\jdupont",
        )

        root = self._parse(xml_bytes)
        ns = {"t": stm._TASK_XML_NS}
        principal = root.find(".//t:Principals/t:Principal", ns)
        assert principal.find("t:UserId", ns).text == "DESKTOP-TEST\\jdupont"

    def test_logon_trigger_is_scoped_to_the_current_user(self) -> None:
        """Régression directe du bug diagnostiqué : sans cet élément, la
        tâche ``onlogon`` était refusée (code 1, « Accès refusé ») pour un
        compte standard."""
        xml_bytes = stm._build_task_xml(
            "C:/StockManager/StockManager.exe", [], schedule=stm.SCHEDULE_ONLOGON, time_of_day="ignorée",
            user_id="DESKTOP-TEST\\jdupont",
        )

        root = self._parse(xml_bytes)
        ns = {"t": stm._TASK_XML_NS}
        trigger = root.find(".//t:Triggers/t:LogonTrigger", ns)
        assert trigger.find("t:UserId", ns).text == "DESKTOP-TEST\\jdupont"

    def test_calendar_trigger_never_carries_a_user_id(self) -> None:
        """Une ``CalendarTrigger`` n'a jamais eu besoin d'être scopée à un
        utilisateur (purement temporelle) — ne pas lui ajouter cet élément,
        jamais utile et non prévu par le schéma pour ce type de
        déclencheur dans cette implémentation."""
        xml_bytes = stm._build_task_xml(
            "C:/StockManager/StockManager.exe", [], schedule=stm.SCHEDULE_DAILY, time_of_day="20:00",
            user_id="DESKTOP-TEST\\jdupont",
        )

        root = self._parse(xml_bytes)
        ns = {"t": stm._TASK_XML_NS}
        trigger = root.find(".//t:Triggers/t:CalendarTrigger", ns)
        assert trigger.find("t:UserId", ns) is None


class TestDefaultCurrentUserId:
    def test_combines_domain_and_username(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("USERDOMAIN", "DESKTOP-TEST")
        monkeypatch.setenv("USERNAME", "jdupont")

        assert stm._default_current_user_id() == "DESKTOP-TEST\\jdupont"

    def test_falls_back_to_username_alone_when_domain_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("USERDOMAIN", raising=False)
        monkeypatch.setenv("USERNAME", "jdupont")

        assert stm._default_current_user_id() == "jdupont"

    def test_never_returns_an_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("USERDOMAIN", raising=False)
        monkeypatch.delenv("USERNAME", raising=False)
        import getpass

        monkeypatch.setattr(getpass, "getuser", lambda: "repli")

        assert stm._default_current_user_id() == "repli"


class TestClassifySchtasksFailure:
    def test_recognizes_french_access_denied(self) -> None:
        diagnosis = stm._classify_schtasks_failure("ERROR: Accès refusé.")

        assert "Accès refusé" in diagnosis

    def test_recognizes_english_access_denied(self) -> None:
        diagnosis = stm._classify_schtasks_failure("ERROR: Access is denied.")

        assert "Accès refusé" in diagnosis

    def test_recognizes_invalid_filename_syntax_as_a_definition_problem(self) -> None:
        """Message Windows réel du tout premier bug de ce module (chemin
        de fichier temporaire XML malformé) — classé comme une définition
        de tâche invalide, jamais confondu avec un refus d'accès."""
        diagnosis = stm._classify_schtasks_failure(
            "ERROR: The filename, directory name, or volume label syntax is incorrect."
        )

        assert "Accès refusé" not in diagnosis
        assert diagnosis

    def test_falls_back_to_a_generic_message_for_unrecognized_errors(self) -> None:
        diagnosis = stm._classify_schtasks_failure("ERREUR : une panne totalement inconnue.")

        assert diagnosis


class TestDescribeExistingTaskConflict:
    def test_no_conflict_when_task_does_not_exist(self) -> None:
        existing = stm.ScheduledTaskStatus(exists=False)

        assert stm._describe_existing_task_conflict(existing, "DESKTOP-TEST\\jdupont") is None

    def test_no_conflict_when_run_as_user_matches_current_user(self) -> None:
        existing = stm.ScheduledTaskStatus(exists=True, run_as_user="DESKTOP-TEST\\jdupont")

        assert stm._describe_existing_task_conflict(existing, "DESKTOP-TEST\\jdupont") is None

    def test_match_is_case_insensitive(self) -> None:
        existing = stm.ScheduledTaskStatus(exists=True, run_as_user="DESKTOP-TEST\\JDupont")

        assert stm._describe_existing_task_conflict(existing, "desktop-test\\jdupont") is None

    def test_reports_a_conflict_when_run_as_user_differs(self) -> None:
        existing = stm.ScheduledTaskStatus(exists=True, run_as_user="DESKTOP-TEST\\autreCompte")

        message = stm._describe_existing_task_conflict(existing, "DESKTOP-TEST\\jdupont")

        assert message is not None
        assert "autreCompte" in message
        assert "n'a pas été supprimée automatiquement" in message

    def test_no_conflict_when_run_as_user_is_unknown(self) -> None:
        """``run_as_user`` absent de la sortie ``schtasks`` (champ non
        rapporté par cette version de Windows) — jamais une fausse alerte
        de conflit à partir d'une absence d'information."""
        existing = stm.ScheduledTaskStatus(exists=True, run_as_user=None)

        assert stm._describe_existing_task_conflict(existing, "DESKTOP-TEST\\jdupont") is None


class TestCreateOrRepairTaskUserIdAndConflict:
    """Intégration (logique pure, ``_run_schtasks`` substitué) des
    mécanismes ci-dessus au sein de ``create_or_repair_task`` lui-même."""

    @pytest.fixture(autouse=True)
    def _force_windows_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(stm.sys, "platform", "win32")

    def test_resolved_user_id_is_embedded_in_the_xml_sent_to_schtasks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess
        from pathlib import Path

        captured = {}

        def _fake_run_schtasks(args):
            if args[0] != "/create":
                # Lecture préalable + relecture de vérification après
                # création (voir ``create_or_repair_task`` et
                # ``_verify_task_registered``) : simulées comme réussies
                # (existence confirmée), relecture XML approfondie omise
                # (sortie vide, best-effort uniquement).
                return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")
            captured["xml_content"] = Path(args[args.index("/xml") + 1]).read_bytes()
            return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(stm, "_run_schtasks", _fake_run_schtasks)

        stm.create_or_repair_task(
            "StockManager - Sauvegarde (ouverture de session)", "C:/StockManager/StockManager.exe", [],
            "20:00", schedule=stm.SCHEDULE_ONLOGON, user_id_resolver=lambda: "DESKTOP-TEST\\jdupont",
        )

        xml_text = captured["xml_content"].decode("utf-16")
        assert "DESKTOP-TEST\\jdupont" in xml_text

    def test_error_message_names_the_conflicting_account_when_task_already_owned_by_another_user(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess

        def _fake_run_schtasks(args):
            if args[0] == "/create":
                return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="Accès refusé.")
            if "/xml" in args:
                return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="")
            # /query sans /xml : état de la tâche existante avant la tentative.
            return subprocess.CompletedProcess(
                args, returncode=0,
                stdout="Status: Ready\nRun As User: DESKTOP-TEST\\autreCompte\n", stderr="",
            )

        monkeypatch.setattr(stm, "_run_schtasks", _fake_run_schtasks)

        with pytest.raises(stm.ScheduledTaskError, match="autreCompte") as excinfo:
            stm.create_or_repair_task(
                "StockManager - Sauvegarde", "C:/StockManager/StockManager.exe", [], "20:00",
                user_id_resolver=lambda: "DESKTOP-TEST\\jdupont",
            )

        assert "Accès refusé" in str(excinfo.value)


class TestVerifyTaskRegistered:
    @pytest.fixture(autouse=True)
    def _force_windows_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(stm.sys, "platform", "win32")

    def test_raises_when_task_does_not_exist_after_a_reported_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mission corrective « Erreur Accès refusé », §5 : jamais de
        succès déclaré sans vérification réelle — même si ``/create`` a
        renvoyé le code 0."""
        import subprocess

        monkeypatch.setattr(
            stm, "_run_schtasks",
            lambda args: subprocess.CompletedProcess(args, returncode=1, stdout="", stderr=""),
        )

        with pytest.raises(stm.ScheduledTaskError, match="relue"):
            stm._verify_task_registered(
                "StockManager - Sauvegarde", executable="C:/StockManager/StockManager.exe",
                schedule=stm.SCHEDULE_DAILY,
            )

    def test_never_fails_when_the_deep_xml_readback_is_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Un échec de la relecture XML approfondie (version de Windows,
        encodage console) ne doit jamais faire échouer une configuration
        par ailleurs réussie — seule l'existence réelle est une condition
        bloquante."""
        import subprocess

        def _fake_run_schtasks(args):
            if "/xml" in args:
                return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="")
            return subprocess.CompletedProcess(args, returncode=0, stdout="Status: Ready", stderr="")

        monkeypatch.setattr(stm, "_run_schtasks", _fake_run_schtasks)

        stm._verify_task_registered(
            "StockManager - Sauvegarde", executable="C:/StockManager/StockManager.exe",
            schedule=stm.SCHEDULE_DAILY,
        )  # ne doit jamais lever.

    def test_never_fails_when_the_xml_readback_is_unparseable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        def _fake_run_schtasks(args):
            if "/xml" in args:
                return subprocess.CompletedProcess(args, returncode=0, stdout="pas du xml valide <<<", stderr="")
            return subprocess.CompletedProcess(args, returncode=0, stdout="Status: Ready", stderr="")

        monkeypatch.setattr(stm, "_run_schtasks", _fake_run_schtasks)

        stm._verify_task_registered(
            "StockManager - Sauvegarde", executable="C:/StockManager/StockManager.exe",
            schedule=stm.SCHEDULE_DAILY,
        )  # ne doit jamais lever.

    def test_raises_when_the_registered_command_does_not_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        xml_with_wrong_command = (
            f'<Task xmlns="{stm._TASK_XML_NS}"><Actions><Exec>'
            f"<Command>C:/Autre/Chemin.exe</Command></Exec></Actions></Task>"
        )

        def _fake_run_schtasks(args):
            if "/xml" in args:
                return subprocess.CompletedProcess(args, returncode=0, stdout=xml_with_wrong_command, stderr="")
            return subprocess.CompletedProcess(args, returncode=0, stdout="Status: Ready", stderr="")

        monkeypatch.setattr(stm, "_run_schtasks", _fake_run_schtasks)

        with pytest.raises(stm.ScheduledTaskError, match="ne correspond pas"):
            stm._verify_task_registered(
                "StockManager - Sauvegarde", executable="C:/StockManager/StockManager.exe",
                schedule=stm.SCHEDULE_DAILY,
            )

    def test_raises_when_the_registered_trigger_type_does_not_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        xml_with_wrong_trigger = (
            f'<Task xmlns="{stm._TASK_XML_NS}"><Triggers><LogonTrigger/></Triggers>'
            f"<Actions><Exec><Command>C:/StockManager/StockManager.exe</Command></Exec></Actions></Task>"
        )

        def _fake_run_schtasks(args):
            if "/xml" in args:
                return subprocess.CompletedProcess(args, returncode=0, stdout=xml_with_wrong_trigger, stderr="")
            return subprocess.CompletedProcess(args, returncode=0, stdout="Status: Ready", stderr="")

        monkeypatch.setattr(stm, "_run_schtasks", _fake_run_schtasks)

        with pytest.raises(stm.ScheduledTaskError, match="type de récurrence"):
            stm._verify_task_registered(
                "StockManager - Sauvegarde", executable="C:/StockManager/StockManager.exe",
                schedule=stm.SCHEDULE_DAILY,  # demande un CalendarTrigger, mais la relecture rapporte LogonTrigger.
            )

    def test_passes_when_registered_command_and_trigger_both_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        xml_matching = (
            f'<Task xmlns="{stm._TASK_XML_NS}"><Triggers><CalendarTrigger/></Triggers>'
            f"<Actions><Exec><Command>C:/StockManager/StockManager.exe</Command></Exec></Actions></Task>"
        )

        def _fake_run_schtasks(args):
            if "/xml" in args:
                return subprocess.CompletedProcess(args, returncode=0, stdout=xml_matching, stderr="")
            return subprocess.CompletedProcess(args, returncode=0, stdout="Status: Ready", stderr="")

        monkeypatch.setattr(stm, "_run_schtasks", _fake_run_schtasks)

        stm._verify_task_registered(
            "StockManager - Sauvegarde", executable="C:/StockManager/StockManager.exe",
            schedule=stm.SCHEDULE_DAILY,
        )  # ne doit jamais lever.


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
        "Run As User:                          DESKTOP-TEST\\user\n"
    )

    def test_extracts_known_fields(self) -> None:
        fields = stm._parse_schtasks_verbose_list(self._SAMPLE_OUTPUT)

        assert fields["status"] == "Ready"
        assert fields["last_run_time"] == "23/11/2026 20:00:03"
        assert fields["last_result"] == "0"
        assert fields["next_run_time"] == "24/11/2026 20:00:00"

    def test_extracts_run_as_user(self) -> None:
        """Mission corrective « Erreur Accès refusé » : permet de détecter
        qu'une tâche existante appartient à un compte différent de
        l'utilisateur courant (voir :func:`stm._describe_existing_task_conflict`)."""
        fields = stm._parse_schtasks_verbose_list(self._SAMPLE_OUTPUT)

        assert fields["run_as_user"] == "DESKTOP-TEST\\user"

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
        """Depuis le passage à ``/xml`` (mission corrective, §3.2), la
        commande ``schtasks`` elle-même ne porte plus ``/sc``/``/st`` — le
        type de déclencheur vit désormais dans le fichier XML référencé
        par ``/xml`` (voir ``TestBuildTaskXml`` pour son contenu) ; ce test
        vérifie que c'est bien ce fichier, portant un ``LogonTrigger``, qui
        est transmis, et qu'il est supprimé après l'appel."""
        import subprocess
        from pathlib import Path

        captured = {}

        def _fake_run_schtasks(args):
            if args[0] != "/create":
                # Lecture préalable de l'état existant, puis relecture de
                # vérification après création (voir ``create_or_repair_task``
                # et ``_verify_task_registered``) — non pertinentes pour ce
                # test, qui vérifie seulement la commande ``/create`` elle-même.
                return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")
            captured["args"] = args
            xml_path = Path(args[args.index("/xml") + 1])
            captured["xml_content"] = xml_path.read_bytes()
            captured["xml_path"] = xml_path
            return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(stm, "_run_schtasks", _fake_run_schtasks)

        stm.create_or_repair_task(
            "StockManager - Sauvegarde (ouverture de session)", "C:/StockManager/StockManager.exe", [],
            "20:00", schedule=stm.SCHEDULE_ONLOGON,
        )

        assert "/sc" not in captured["args"]  # porté par le XML désormais, jamais en ligne de commande
        assert "/st" not in captured["args"]
        assert "LogonTrigger" in captured["xml_content"].decode("utf-16")
        assert not captured["xml_path"].exists()  # fichier temporaire toujours nettoyé après l'appel

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


# -- mission « Détails de la tâche planifiée Windows » ------------------------------
#
# ``_FIELD_MAP``/``_parse_schtasks_verbose_list`` sont analysés par un poste
# Windows en anglais (voir leur docstring, corrigée) : sur un poste dans une
# autre langue, ``last_run_time``/``last_result``/``next_run_time`` restaient
# silencieusement ``None`` (« Non disponible » affiché), alors que la tâche
# existe bel et bien et s'exécute normalement. Les fonctions ci-dessous
# (``describe_task_result``/``describe_last_run_time``/``describe_next_run_time``/
# ``query_task_runtime_info``) remplacent cette voie par un relevé structuré
# (PowerShell, ``Get-ScheduledTaskInfo``) — jamais affecté par la langue
# d'affichage Windows.


class TestDescribeTaskResult:
    """§C du mandat : conversion du code numérique ``LastTaskResult`` en un
    libellé compréhensible — pure, sans aucun appel Windows."""

    def test_zero_means_success(self) -> None:
        assert stm.describe_task_result(0) == "Réussite"

    def test_none_means_never_run(self) -> None:
        assert stm.describe_task_result(None) == "Jamais exécutée"

    def test_sched_s_task_has_not_run_means_never_run(self) -> None:
        """Code officiellement documenté par Microsoft pour ce cas précis
        (0x00041303) — jamais déduit d'une absence de valeur seule."""
        assert stm.describe_task_result(stm.TASK_RESULT_NEVER_RUN) == "Jamais exécutée"
        assert stm.TASK_RESULT_NEVER_RUN == 267011

    def test_known_failure_codes_are_prefixed_with_echec(self) -> None:
        for code in (1, 2, 5, 0x80070002, 0x80070005):
            description = stm.describe_task_result(code)
            assert description.startswith("Échec – "), description

    def test_unknown_code_is_reported_as_such_rather_than_guessed(self) -> None:
        assert stm.describe_task_result(123456789) == "Résultat inconnu (code : 123456789)"


class TestDescribeLastRunTime:
    """§A du mandat : jamais une date factice pour une tâche jamais
    exécutée."""

    def test_never_run_via_last_task_result_ignores_any_sentinel_date(self) -> None:
        from datetime import datetime

        sentinel_date = datetime(1999, 11, 30)  # date sentinelle Windows connue, jamais une vraie exécution.
        assert (
            stm.describe_last_run_time(sentinel_date, stm.TASK_RESULT_NEVER_RUN) == "Jamais exécutée"
        )

    def test_missing_last_run_time_means_never_run(self) -> None:
        assert stm.describe_last_run_time(None, None) == "Jamais exécutée"

    def test_real_last_run_time_is_formatted_in_french_convention(self) -> None:
        from datetime import datetime

        formatted = stm.describe_last_run_time(datetime(2026, 11, 28, 8, 40, 4), 0)

        assert formatted == "28/11/2026 08:40:04"


class TestDescribeNextRunTime:
    """§B du mandat : jamais de calcul artificiel, uniquement ce que
    rapporte déjà le Planificateur de tâches Windows lui-même."""

    def test_none_is_reported_explicitly(self) -> None:
        assert stm.describe_next_run_time(None) == "Aucune prochaine exécution prévue."

    def test_real_next_run_time_is_formatted_in_french_convention(self) -> None:
        from datetime import datetime

        formatted = stm.describe_next_run_time(datetime(2026, 11, 29, 12, 45, 0))

        assert formatted == "29/11/2026 12:45:00"


@_skip_on_windows
def test_query_task_runtime_info_refuses_outside_windows() -> None:
    with pytest.raises(UnsupportedPlatformError):
        stm.query_task_runtime_info("StockManager - Sauvegarde automatique")


class TestQueryTaskRuntimeInfo:
    """Mission « Détails de la tâche planifiée Windows » : relevé structuré
    via PowerShell plutôt que l'analyse de texte localisé de ``schtasks /fo
    list /v`` — ``_run_powershell`` est substitué par un résultat
    synthétique, jamais un appel réel à ``powershell.exe`` (même convention
    que ``TestErrorTranslation`` pour ``_run_schtasks``)."""

    @pytest.fixture(autouse=True)
    def _force_windows_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(stm.sys, "platform", "win32")

    def test_returns_available_info_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        payload = (
            '{"LastRunTime":"2026-11-28T08:40:04+00:00",'
            '"NextRunTime":"2026-11-29T12:45:00+00:00","LastTaskResult":0}'
        )
        monkeypatch.setattr(
            stm, "_run_powershell",
            lambda args: subprocess.CompletedProcess(args, returncode=0, stdout=payload, stderr=""),
        )

        info = stm.query_task_runtime_info("StockManager - Sauvegarde automatique")

        assert info.available is True
        assert info.error is None
        assert info.last_task_result == 0
        assert info.last_run_time is not None and info.last_run_time.year == 2026
        assert info.next_run_time is not None and info.next_run_time.day == 29

    def test_reports_never_run_via_last_task_result_even_without_a_date(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess

        payload = '{"LastRunTime":null,"NextRunTime":"2026-11-29T12:45:00+00:00","LastTaskResult":267011}'
        monkeypatch.setattr(
            stm, "_run_powershell",
            lambda args: subprocess.CompletedProcess(args, returncode=0, stdout=payload, stderr=""),
        )

        info = stm.query_task_runtime_info("StockManager - Sauvegarde automatique")

        assert info.available is True
        assert info.last_run_time is None
        assert info.last_task_result == stm.TASK_RESULT_NEVER_RUN

    def test_reports_no_next_run_time_as_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        payload = '{"LastRunTime":"2026-11-28T08:40:04+00:00","NextRunTime":null,"LastTaskResult":0}'
        monkeypatch.setattr(
            stm, "_run_powershell",
            lambda args: subprocess.CompletedProcess(args, returncode=0, stdout=payload, stderr=""),
        )

        info = stm.query_task_runtime_info("StockManager - Sauvegarde automatique")

        assert info.next_run_time is None

    def test_returns_unavailable_on_non_zero_return_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        monkeypatch.setattr(
            stm, "_run_powershell",
            lambda args: subprocess.CompletedProcess(
                args, returncode=1, stdout="", stderr="Get-ScheduledTaskInfo : tâche introuvable.",
            ),
        )

        info = stm.query_task_runtime_info("StockManager - Sauvegarde automatique")

        assert info.available is False
        assert info.last_run_time is None
        assert "tâche introuvable" in info.error

    def test_returns_unavailable_on_unreadable_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        monkeypatch.setattr(
            stm, "_run_powershell",
            lambda args: subprocess.CompletedProcess(args, returncode=0, stdout="ceci n'est pas du JSON", stderr=""),
        )

        info = stm.query_task_runtime_info("StockManager - Sauvegarde automatique")

        assert info.available is False
        assert info.error is not None

    def test_returns_unavailable_when_powershell_cannot_be_executed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Substitue directement ``_run_powershell`` (plutôt que
        ``subprocess.run``, voir ``test_run_powershell_translates_missing_binary_to_scheduled_task_error``
        pour ce niveau) : ``no_console_window_kwargs`` lit le ``sys.platform``
        réel du processus, que cette classe force par ailleurs à ``win32``
        pour franchir ``_ensure_windows`` — l'atteindre réellement ici
        casserait ce test sous Linux, sans aucun rapport avec le
        comportement vérifié."""
        def _raise(args):
            raise stm.ScheduledTaskError("Impossible d'exécuter powershell.exe : introuvable.")

        monkeypatch.setattr(stm, "_run_powershell", _raise)

        info = stm.query_task_runtime_info("StockManager - Sauvegarde automatique")

        assert info.available is False
        assert "powershell.exe" in info.error

    def test_escapes_single_quotes_in_task_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Défense en profondeur : même si le nom de tâche de l'application
        ne contient jamais de guillemet simple, le script PowerShell généré
        ne doit jamais être cassé par un caractère imprévu."""
        import subprocess

        captured = {}

        def _fake_run_powershell(args):
            captured["script"] = args[0]
            return subprocess.CompletedProcess(args, returncode=0, stdout="{}", stderr="")

        monkeypatch.setattr(stm, "_run_powershell", _fake_run_powershell)
        task_name = "Tâche d'un ''utilisateur''"

        stm.query_task_runtime_info(task_name)

        # Chaque guillemet simple double (convention PowerShell), jamais
        # transmis tel quel — calculé ici plutôt qu'écrit en dur pour ne
        # jamais dépendre d'un comptage manuel des guillemets.
        assert f"'{task_name.replace(chr(39), chr(39) * 2)}'" in captured["script"]


def test_run_powershell_translates_missing_binary_to_scheduled_task_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_run_powershell`` lui-même n'appelle jamais ``_ensure_windows`` (ce
    sont ses appelants qui le font) — même convention que
    ``test_run_schtasks_translates_missing_binary_to_scheduled_task_error``."""

    def _raise_missing_binary(*args, **kwargs):
        raise FileNotFoundError("powershell introuvable")

    monkeypatch.setattr(stm.subprocess, "run", _raise_missing_binary)

    with pytest.raises(stm.ScheduledTaskError):
        stm._run_powershell(["Get-ScheduledTaskInfo -TaskName 'x'"])

"""Tests de ``app.services.dashboard.dashboard_preferences`` (Mission 3,
§6.2-6.3) : stockage local, par utilisateur, des KPI sélectionnés sur le
Dashboard."""
from dataclasses import replace

from app.config.settings import get_settings
from app.services.dashboard.dashboard_preferences import load_selected_kpis, save_selected_kpis


def _settings_in(tmp_path):
    base = get_settings()
    return replace(base, db_path=tmp_path / "ignored.db")


def test_load_returns_none_when_never_customized(tmp_path) -> None:
    settings = _settings_in(tmp_path)

    assert load_selected_kpis("alice", settings) is None


def test_save_then_load_round_trips(tmp_path) -> None:
    settings = _settings_in(tmp_path)

    save_selected_kpis("alice", ["articles", "rental_amount"], settings)

    assert load_selected_kpis("alice", settings) == ["articles", "rental_amount"]


def test_preferences_are_kept_per_username(tmp_path) -> None:
    settings = _settings_in(tmp_path)

    save_selected_kpis("alice", ["articles"], settings)
    save_selected_kpis("bob", ["rental_count", "rental_amount"], settings)

    assert load_selected_kpis("alice", settings) == ["articles"]
    assert load_selected_kpis("bob", settings) == ["rental_count", "rental_amount"]


def test_saving_again_overwrites_previous_selection_for_same_user(tmp_path) -> None:
    settings = _settings_in(tmp_path)

    save_selected_kpis("alice", ["articles", "stock_value"], settings)
    save_selected_kpis("alice", ["sales_amount"], settings)

    assert load_selected_kpis("alice", settings) == ["sales_amount"]


def test_load_returns_none_for_corrupted_file(tmp_path) -> None:
    settings = _settings_in(tmp_path)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "dashboard_preferences.json").write_text("not valid json {", encoding="utf-8")

    assert load_selected_kpis("alice", settings) is None


def test_load_returns_none_when_value_is_not_a_list(tmp_path) -> None:
    settings = _settings_in(tmp_path)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "dashboard_preferences.json").write_text('{"alice": "not-a-list"}', encoding="utf-8")

    assert load_selected_kpis("alice", settings) is None

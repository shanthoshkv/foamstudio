from __future__ import annotations

import pytest

from foamstudio.core.settings_model import SettingsModel, load_settings


def test_defaults_are_valid() -> None:
    SettingsModel().validate()


def test_rejects_unknown_theme() -> None:
    with pytest.raises(ValueError, match="neon"):
        SettingsModel(theme="neon").validate()


def test_rejects_font_outside_range() -> None:
    with pytest.raises(ValueError, match="7"):
        SettingsModel(font_point_size=7).validate()


def test_repairs_bad_stored_values() -> None:
    loaded = load_settings("neon", "large", "maybe")
    assert loaded.model.theme == "dark"
    assert loaded.model.font_point_size == 10
    assert loaded.model.expert_mode is False
    assert loaded.error is not None
    assert "neon" in loaded.error
    assert "large" in loaded.error
    assert "maybe" in loaded.error


def test_clamps_font_and_accepts_string_bools() -> None:
    loaded = load_settings("light", "99", "yes")
    assert loaded.model.theme == "light"
    assert loaded.model.font_point_size == 24
    assert loaded.model.expert_mode is True
    assert loaded.error is not None
    assert "99" in loaded.error


def test_keeps_clean_values() -> None:
    loaded = load_settings("light", 12, False)
    assert loaded.error is None
    assert loaded.model == SettingsModel("light", 12, False)

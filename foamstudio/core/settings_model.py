"""Settings values with no Qt dependency."""

from __future__ import annotations

from dataclasses import dataclass

THEMES = ("dark", "light")
MIN_FONT_PT = 8
MAX_FONT_PT = 24
DEFAULT_FONT_PT = 10


@dataclass(frozen=True)
class SettingsModel:
    theme: str = "dark"
    font_point_size: int = DEFAULT_FONT_PT
    expert_mode: bool = False
    crash_reports: bool = False

    def validate(self) -> None:
        if self.theme not in THEMES:
            raise ValueError(f"Unknown theme {self.theme!r}. Expected one of {THEMES}.")
        if self.font_point_size < MIN_FONT_PT or self.font_point_size > MAX_FONT_PT:
            raise ValueError(
                f"Font size {self.font_point_size} is outside {MIN_FONT_PT}–{MAX_FONT_PT}."
            )


@dataclass(frozen=True)
class LoadedSettings:
    model: SettingsModel
    error: str | None = None


def _parse_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _parse_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return value == 1
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return None


def load_settings(
    theme: object,
    font_point_size: object,
    expert_mode: object,
    crash_reports: object = False,
) -> LoadedSettings:
    """Return a valid model. `error` describes every stored value that was rejected."""
    problems: list[str] = []

    if isinstance(theme, str) and theme in THEMES:
        theme_ok = theme
    else:
        problems.append(f"theme {theme!r} is not one of {THEMES}; using dark")
        theme_ok = "dark"

    size = _parse_int(font_point_size)
    if size is None:
        problems.append(f"font size {font_point_size!r} is not an integer; using {DEFAULT_FONT_PT}")
        size_ok = DEFAULT_FONT_PT
    elif size < MIN_FONT_PT or size > MAX_FONT_PT:
        size_ok = min(max(size, MIN_FONT_PT), MAX_FONT_PT)
        problems.append(f"font size {size} is outside {MIN_FONT_PT}–{MAX_FONT_PT}; using {size_ok}")
    else:
        size_ok = size

    expert = _parse_bool(expert_mode)
    if expert is None:
        problems.append(f"expert mode {expert_mode!r} is not a boolean; using off")
        expert_ok = False
    else:
        expert_ok = expert

    reports = _parse_bool(crash_reports)
    if reports is None:
        problems.append(f"crash reports {crash_reports!r} is not a boolean; using off")
        reports_ok = False
    else:
        reports_ok = reports

    model = SettingsModel(
        theme=theme_ok,
        font_point_size=size_ok,
        expert_mode=expert_ok,
        crash_reports=reports_ok,
    )
    model.validate()
    error = " ".join(problems) if problems else None
    return LoadedSettings(model=model, error=error)

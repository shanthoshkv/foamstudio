"""QSettings adapter. The values themselves live in core.settings_model."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from PySide6.QtCore import QSettings

from foamstudio.core.paths import state_dir
from foamstudio.core.runtime.model import Installation
from foamstudio.core.settings_model import LoadedSettings, SettingsModel, load_settings

logger = logging.getLogger("foamstudio")


def default_store() -> QSettings:
    if os.environ.get("FOAMSTUDIO_STATE_DIR"):
        path = state_dir() / "settings.ini"
        path.parent.mkdir(parents=True, exist_ok=True)
        return QSettings(str(path), QSettings.Format.IniFormat)
    return QSettings("FoamStudio", "FoamStudio")


class AppSettings:
    def __init__(self, store: QSettings | None = None) -> None:
        self._store = default_store() if store is None else store

    @property
    def path(self) -> str:
        return str(Path(self._store.fileName()))

    def load(self) -> SettingsModel:
        loaded: LoadedSettings = load_settings(
            self._store.value("theme", "dark"),
            self._store.value("font_point_size", 10),
            self._store.value("expert_mode", False),
            self._store.value("crash_reports", False),
        )
        if loaded.error:
            logger.error("Saved settings were repaired: %s", loaded.error)
        return loaded.model

    def save(self, model: SettingsModel) -> None:
        model.validate()
        self._store.setValue("theme", model.theme)
        self._store.setValue("font_point_size", model.font_point_size)
        self._store.setValue("expert_mode", model.expert_mode)
        self._store.setValue("crash_reports", model.crash_reports)
        self._sync()

    def load_runtime(self) -> Installation | None:
        raw = self._store.value("runtime", "")
        if raw in ("", None):
            return None
        if not isinstance(raw, str):
            logger.error("Saved runtime was ignored: value is %s.", type(raw).__name__)
            return None
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("Saved runtime was ignored: %s", exc)
            return None
        try:
            return Installation.from_dict(loaded)
        except ValueError as exc:
            logger.error("Saved runtime was ignored: %s", exc)
            return None

    def save_runtime(self, installation: Installation) -> None:
        payload = json.dumps(installation.to_dict(), sort_keys=True)
        self._store.setValue("runtime", payload)
        self._sync()

    def wizard_done(self) -> bool:
        raw = self._store.value("wizard_done", False)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, int) and raw in (0, 1):
            return bool(raw)
        if isinstance(raw, str):
            lowered = raw.strip().lower()
            if lowered in {"1", "true", "yes"}:
                return True
            if lowered in {"0", "false", "no"}:
                return False
        logger.error("Saved wizard flag %r was ignored.", raw)
        return False

    def set_wizard_done(self, done: bool) -> None:
        self._store.setValue("wizard_done", bool(done))
        self._sync()

    def _sync(self) -> None:
        self._store.sync()
        status = self._store.status()
        if status != QSettings.Status.NoError:
            raise OSError(f"Could not save settings to {self._store.fileName()} (status {status}).")

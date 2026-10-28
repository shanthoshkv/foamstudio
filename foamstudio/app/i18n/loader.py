"""Load a compiled catalog when FOAMSTUDIO_LANG names one.

English needs no catalog: the source strings are English. Any other language
must have `foamstudio_<lang>.qm` or the failure is logged.
"""

from __future__ import annotations

import logging
import os
from importlib.resources import as_file, files

from PySide6.QtCore import QLocale, QTranslator
from PySide6.QtWidgets import QApplication

logger = logging.getLogger("foamstudio")


def language_name() -> str:
    override = os.environ.get("FOAMSTUDIO_LANG")
    if override:
        return override
    return QLocale.system().name()


def install_translators(app: QApplication) -> list[QTranslator]:
    lang = language_name()
    if lang.lower().startswith("en"):
        return []
    stem = lang.split("_", 1)[0]
    resource = files("foamstudio.app.i18n").joinpath(f"foamstudio_{stem}.qm")
    if not resource.is_file():
        logger.error(
            "No translation catalog for language %s. Expected foamstudio_%s.qm. "
            "The interface stays in English.",
            lang,
            stem,
        )
        return []
    translator = QTranslator(app)
    with as_file(resource) as path:
        loaded = translator.load(str(path))
    if not loaded:
        logger.error("Translation catalog %s failed to load.", resource)
        return []
    app.installTranslator(translator)
    return [translator]

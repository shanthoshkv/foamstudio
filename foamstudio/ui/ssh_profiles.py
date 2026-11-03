"""Saved SSH/cluster machines: test the connection, then use one as the runtime."""

from __future__ import annotations

import json
import subprocess

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from foamstudio.app.settings import AppSettings
from foamstudio.core.runtime.model import Installation
from foamstudio.core.runtime.native import classify_bashrc

_KEY = "ssh/profiles"
_FIELDS = ("name", "host", "user", "bashrc", "remote_case", "scheduler")


def load_profiles(settings: AppSettings) -> list[dict[str, str]]:
    try:
        data = json.loads(str(settings._store.value(_KEY, "[]")))
    except json.JSONDecodeError:
        return []
    return [p for p in data if isinstance(p, dict)]


def to_installation(profile: dict[str, str]) -> Installation:
    kind = classify_bashrc(profile.get("bashrc", "")) or ("esi", "unknown")
    return Installation.from_dict(
        {
            "kind": "ssh",
            "flavour": kind[0],
            "version": kind[1],
            **{
                k: profile.get(k, "")
                for k in ("bashrc", "host", "user", "remote_case", "scheduler")
            },
        }
    )


class SshProfiles(QWidget):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sshProfiles")
        self._settings = settings
        self.profiles = QComboBox()
        self.fields = {f: QLineEdit() for f in _FIELDS}
        self.fields["bashrc"].setText("/usr/lib/openfoam/openfoam2412/etc/bashrc")
        self.fields["remote_case"].setPlaceholderText(
            "/scratch/you/case  (where the case is copied)"
        )
        self.fields["scheduler"].setPlaceholderText("empty, slurm or pbs")
        self.fields["name"].setPlaceholderText("lab cluster")
        self.result = QLabel(
            self.tr("Saved machines appear above. Key-based ssh login is required.")
        )
        self.result.setWordWrap(True)
        form = QFormLayout()
        for f, w in self.fields.items():
            form.addRow(f.replace("_", " ").capitalize(), w)
        row = QHBoxLayout()
        for label, slot in (
            (self.tr("Test connection"), self._test),
            (self.tr("Save"), self._save),
            (self.tr("Use as runtime"), self._use),
            (self.tr("Delete"), self._delete),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda _c=False, s=slot: s())
            row.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.profiles)
        layout.addLayout(form)
        layout.addLayout(row)
        layout.addWidget(self.result, 1)
        self.profiles.currentIndexChanged.connect(self._fill)
        self._reload()

    def _current(self) -> dict[str, str]:
        return {f: w.text().strip() for f, w in self.fields.items()}

    def _reload(self) -> None:
        self.profiles.blockSignals(True)
        self.profiles.clear()
        self.profiles.addItem(self.tr("New machine..."), None)
        for p in load_profiles(self._settings):
            self.profiles.addItem(
                f"{p.get('name') or p.get('host')}  ({p.get('user')}@{p.get('host')})", p
            )
        self.profiles.blockSignals(False)

    def _fill(self, _index: int) -> None:
        profile = self.profiles.currentData() or {}
        for f, w in self.fields.items():
            w.setText(profile.get(f, ""))

    def _test(self) -> None:
        p = self._current()
        try:
            to_installation(p)
            done = subprocess.run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=8",
                    f"{p['user']}@{p['host']}",
                    f"test -f '{p['bashrc']}' && echo bashrc-ok || echo bashrc-missing",
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
            self.result.setText(str(exc))
            return
        out = (done.stdout + done.stderr).strip()
        ok = done.returncode == 0 and "bashrc-ok" in out
        self.result.setText(
            ("Connected; OpenFOAM bashrc found." if ok else "Failed:\n") + ("" if ok else out)
        )

    def _save(self) -> None:
        p = self._current()
        if not p["host"] or not p["user"]:
            self.result.setText(self.tr("Host and user are required."))
            return
        rest = [
            q
            for q in load_profiles(self._settings)
            if (q.get("host"), q.get("user")) != (p["host"], p["user"])
        ]
        self._settings._store.setValue(_KEY, json.dumps([*rest, p]))
        self._reload()
        self.profiles.setCurrentIndex(self.profiles.count() - 1)
        self.result.setText(self.tr("Saved."))

    def _delete(self) -> None:
        p = self._current()
        keep = [
            q
            for q in load_profiles(self._settings)
            if (q.get("host"), q.get("user")) != (p["host"], p["user"])
        ]
        self._settings._store.setValue(_KEY, json.dumps(keep))
        self._reload()

    def _use(self) -> None:
        try:
            installation = to_installation(self._current())
            self._settings.save_runtime(installation)
        except (ValueError, OSError) as exc:
            self.result.setText(str(exc))
            return
        self.result.setText(f"Runtime saved: {installation.label()}")

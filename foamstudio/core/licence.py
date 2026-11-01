"""Offline subscription licence keys. Qt-free, stdlib only.

A key is ``<base64url payload>.<base64url signature>``. The payload is JSON
``{"email", "plan", "expires": "YYYY-MM-DD", "seats"}``. The signature is RSA over the
payload's SHA-256 (full-domain hash), checked with the public modulus below. Only the
vendor's private key (``scripts/issue_licence.py``, kept outside the repository) signs keys.

Without a key FoamStudio runs as a TRIAL_DAYS trial counted from the first launch.
ponytail: the trial start lives in the state dir, so deleting it restarts the trial;
move it to a signed server check if that matters.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from foamstudio.core.paths import state_dir

E = 65537
PUBLIC_N = int(
    "7c8639a0aca6569519b2e2147ff94a7c108f6d350545ece162d65062716a4137ee55b74e89a1f974a82e6be45fb4b3abe079f717d94c9d8124da8ccb3b1b69a9f9c6a556dc76dc7ccef247b4d4b081ae85a5a062a83f856e871c99d8d8a4fb3fe946d86c0957874b3a438c6b3615175c471f114ed63059123163fc6c4aaae7ee1e73e0b14368bf564b8943bdcff33e636928615567f10effbb5b9f75296144e4b41f4baa2645945393ff960dda47ef562bdd63c0020421a1a9b57c5f29f8dca1cfe75b3edf3a5fb250a634c7a4a1fff4329e2e65441861d91f842e12a05ee3b787719e4e2a7c28acbac00a23b52b4bb95c91df5d8c3511e1be08941938d909d1",
    16,
)
TRIAL_DAYS = 30


class LicenceError(ValueError):
    pass


@dataclass(frozen=True)
class Licence:
    email: str
    plan: str
    expires: date
    seats: int


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def digest_int(payload: bytes, modulus: int) -> int:
    """SHA-256 expanded to the modulus size (MGF1-style counter), reduced mod n."""
    size = (modulus.bit_length() + 7) // 8
    out = b""
    counter = 0
    while len(out) < size:
        out += hashlib.sha256(payload + counter.to_bytes(4, "big")).digest()
        counter += 1
    return int.from_bytes(out[:size], "big") % modulus


def verify(key: str, *, modulus: int = PUBLIC_N, today: date | None = None) -> Licence:
    if modulus <= 1:
        raise LicenceError("This build has no licence public key. Use a release build.")
    try:
        body, sig = key.strip().split(".")
        payload = _b64d(body)
        signature = int.from_bytes(_b64d(sig), "big")
    except ValueError as exc:
        raise LicenceError("The licence key is not in the expected format.") from exc
    if pow(signature, E, modulus) != digest_int(payload, modulus):
        raise LicenceError("The licence key signature is invalid.")
    data = json.loads(payload)
    lic = Licence(
        str(data["email"]),
        str(data["plan"]),
        date.fromisoformat(data["expires"]),
        int(data["seats"]),
    )
    if lic.expires < (today or date.today()):
        raise LicenceError(f"The licence for {lic.email} expired on {lic.expires}. Renew it.")
    return lic


def key_path() -> Path:
    return state_dir() / "licence.key"


def save_key(key: str) -> Licence:
    lic = verify(key, modulus=PUBLIC_N)
    key_path().parent.mkdir(parents=True, exist_ok=True)
    key_path().write_text(key.strip() + "\n", encoding="utf-8")
    return lic


def status(today: date | None = None) -> tuple[bool, str]:
    """(may run solvers, message for the status bar)."""
    today = today or date.today()
    if key_path().is_file():
        try:
            lic = verify(key_path().read_text(encoding="utf-8"), modulus=PUBLIC_N, today=today)
        except LicenceError as exc:
            return False, str(exc)
        return True, f"Licensed to {lic.email} ({lic.plan}) until {lic.expires}"
    start_file = state_dir() / "trial.start"
    if not start_file.is_file():
        start_file.parent.mkdir(parents=True, exist_ok=True)
        start_file.write_text(today.isoformat(), encoding="utf-8")
    start = date.fromisoformat(start_file.read_text(encoding="utf-8").strip())
    left = (start + timedelta(days=TRIAL_DAYS) - today).days
    if left < 0:
        return False, "The trial has ended. Help → Enter licence key... to continue running cases."
    return True, f"Trial: {left} days left"

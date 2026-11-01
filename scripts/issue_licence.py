"""Vendor tool: create the signing key pair once, then sign subscription licence keys.

    python scripts/issue_licence.py --init               # writes ~/.foamstudio-signing/private.json
    python scripts/issue_licence.py EMAIL PLAN YYYY-MM-DD [SEATS]

--init also writes the public modulus into foamstudio/core/licence.py. Keep private.json
out of the repository and backed up: losing it means every key must be reissued.
"""

from __future__ import annotations

import base64
import json
import re
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foamstudio.core.licence import E, digest_int, verify  # noqa: E402

PRIVATE = Path.home() / ".foamstudio-signing" / "private.json"
LICENCE_PY = Path(__file__).resolve().parents[1] / "foamstudio" / "core" / "licence.py"


def _probable_prime(bits: int) -> int:
    small = (3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    while True:
        n = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if any(n % p == 0 for p in small):
            continue
        d, r = n - 1, 0
        while d % 2 == 0:
            d, r = d // 2, r + 1
        for _ in range(40):
            x = pow(secrets.randbelow(n - 3) + 2, d, n)
            if x in (1, n - 1):
                continue
            for _ in range(r - 1):
                x = pow(x, 2, n)
                if x == n - 1:
                    break
            else:
                break
        else:
            return n


def init() -> None:
    if PRIVATE.exists():
        sys.exit(f"{PRIVATE} exists. Delete it only if you mean to invalidate every key.")
    while True:
        p, q = _probable_prime(1024), _probable_prime(1024)
        phi = (p - 1) * (q - 1)
        if p != q and phi % E:
            break
    n, d = p * q, pow(E, -1, phi)
    PRIVATE.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE.write_text(json.dumps({"n": hex(n), "d": hex(d)}), encoding="utf-8")
    text = LICENCE_PY.read_text(encoding="utf-8")
    text = re.sub(
        r"PUBLIC_N = int\(\n.*?\n    16,\n\)",
        f'PUBLIC_N = int(\n    "{n:x}",\n    16,\n)',
        text,
        flags=re.S,
    )
    LICENCE_PY.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {PRIVATE} and the public modulus into {LICENCE_PY}")


def issue(email: str, plan: str, expires: str, seats: int) -> str:
    keys = json.loads(PRIVATE.read_text(encoding="utf-8"))
    n, d = int(keys["n"], 16), int(keys["d"], 16)
    payload = json.dumps(
        {"email": email, "plan": plan, "expires": expires, "seats": seats}, separators=(",", ":")
    ).encode()
    sig = pow(digest_int(payload, n), d, n)

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    key = f"{b64(payload)}.{b64(sig.to_bytes((n.bit_length() + 7) // 8, 'big'))}"
    verify(key, modulus=n)
    return key


if __name__ == "__main__":
    if sys.argv[1:] == ["--init"]:
        init()
    elif len(sys.argv) in (4, 5):
        print(
            issue(
                sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) == 5 else 1
            )
        )
    else:
        sys.exit(__doc__)

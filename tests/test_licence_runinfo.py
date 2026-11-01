from __future__ import annotations

import base64
import json
from datetime import date
from pathlib import Path

import pytest

from foamstudio.core import licence, runinfo
from foamstudio.core.mesh.airfoil import Naca4, airfoil_spec, c_mesh


def _key(n: int, d: int, expires: str) -> str:
    payload = json.dumps({"email": "a@b.c", "plan": "pro", "expires": expires, "seats": 1}).encode()
    sig = pow(licence.digest_int(payload, n), d, n)

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{b64(payload)}.{b64(sig.to_bytes(64, 'big'))}"


def test_licence_verify_and_trial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p, q = 2**127 - 1, 2**89 - 1  # Mersenne primes
    n, d = p * q, pow(licence.E, -1, (p - 1) * (q - 1))
    good = _key(n, d, "2030-01-01")
    assert licence.verify(good, modulus=n, today=date(2029, 1, 1)).email == "a@b.c"
    with pytest.raises(licence.LicenceError, match="expired"):
        licence.verify(good, modulus=n, today=date(2031, 1, 1))
    with pytest.raises(licence.LicenceError, match="signature"):
        licence.verify(good[:-4] + "AAAA", modulus=n)
    with pytest.raises(licence.LicenceError, match="format"):
        licence.verify("nonsense", modulus=n)
    monkeypatch.setenv("FOAMSTUDIO_STATE_DIR", str(tmp_path))
    assert licence.status(date(2026, 1, 1)) == (True, "Trial: 30 days left")
    assert not licence.status(date(2026, 3, 1))[0]
    monkeypatch.setattr(licence, "PUBLIC_N", n)
    licence.key_path().write_text(good, encoding="utf-8")
    allowed, message = licence.status(date(2029, 1, 1))
    assert allowed and "a@b.c" in message


def test_runinfo(tmp_path: Path) -> None:
    assert runinfo.suggest_processes(89_600, 6) == 4
    assert runinfo.suggest_processes(1_000, 6) == 1
    log = "".join(
        f"Time = {i}\n\nExecutionTime = {i * 0.5} s  ClockTime = 1 s\n" for i in range(1, 101)
    )
    prog = runinfo.progress(log, 300)
    assert prog is not None and prog.per_second == pytest.approx(2.0) and prog.eta_seconds == 100
    assert "startFrom latestTime" in runinfo.explain('cannot find file "/x/processor3/0/p"')
    assert runinfo.explain("all fine") == ""
    poly = tmp_path / "constant" / "polyMesh"
    (poly / "sets").mkdir(parents=True)
    head = "FoamFile\n{\n    class %s;\n}\n\n"
    (poly / "owner").write_text(head % "labelList" + "3\n(\n5\n6\n7\n)\n", encoding="utf-8")
    (poly / "sets" / "nonOrthoFaces").write_text(
        head % "faceSet" + "2\n(\n0\n2\n)\n", encoding="utf-8"
    )
    (poly / "sets" / "highAspectRatioCells").write_text(
        head % "cellSet" + "1\n(\n4\n)\n", encoding="utf-8"
    )
    assert runinfo.bad_cells(tmp_path) == {"highAspectRatioCells": [4], "nonOrthoFaces": [5, 7]}
    post = tmp_path / "postProcessing" / "forceCoeffs1" / "0"
    post.mkdir(parents=True)
    (post / "coefficient.dat").write_text(
        "# Time Cd Cl\n1 0.01 0.5\n2 0.009 0.52\n", encoding="utf-8"
    )
    assert runinfo.coefficients(tmp_path)["Cl"] == [0.5, 0.52]


def test_airfoil() -> None:
    assert Naca4("2412").surface(0.4, 1)[1] > Naca4("0012").surface(0.4, 1)[1]
    with pytest.raises(ValueError):
        Naca4("12")
    text = c_mesh("0012", 4e-6, 0.5)
    assert text.count("hex (") == 12 and "airfoil" in text
    spec = airfoil_spec("0012", 10, 3e6)
    far = next(p for p in spec["state"]["patches"] if p["role"] == "inlet")
    assert far["fields"]["U"]["Uy"] == pytest.approx(0.17364817766693)
    assert spec["state"]["nu"] == pytest.approx(1 / 3e6) and spec["state"]["forces"]

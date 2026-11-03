"""Unit checks for core.physics and core.studies (OpenFOAM parse: scripts/physics_check.py)."""

import math

import pytest

from foamstudio.core import physics as P
from foamstudio.core import studies as S


def balanced(text: str) -> bool:
    return all(text.count(a) == text.count(b) for a, b in ("{}", "()"))


def test_isa_matches_1976_tables() -> None:
    T, p, _rho, _a = P.isa(11000)
    assert abs(T - 216.77) < 0.05 and abs(p - 22700) / 22700 < 0.002
    T, p, _rho, _a = P.isa(30000)
    assert abs(T - 226.51) < 0.05 and abs(p - 1197.0) / 1197 < 0.003


def test_writers_are_balanced_dictionaries() -> None:
    texts = [
        P.mrf("rotor", (0, 0, 0), (0, 0, 1), 35000, ["casing"]),
        P.solid_body_rotation("rotor", (0, 0, 0), (1, 0, 0), 100),
        P.topo_set(
            [
                {
                    "name": "a",
                    "kind": "box",
                    "min": (0, 0, 0),
                    "max": (1, 1, 1),
                    "within": "w",
                    "zone": True,
                }
            ]
        ),
        P.create_patch(["a"], "wall"),
        P.set_fields({"T": "300"}, [{"box": ((0, 0, 0), (1, 1, 1)), "values": {"T": "600"}}]),
        P.turbulence("kOmegaSST"),
        P.turbulence("WALE"),
        P.function_objects(["schlieren", "Q", "forces", "pumpHead", "probes"]),
        P.peng_robinson("CH4", 3500, 1e-4),
        P.layer_controls(10, 1e-5, 1.2, ["wall"]),
    ]
    assert all(balanced(t) for t in texts)
    assert "omega       3665.191429" in texts[0]  # 35000 rpm in rad/s


def test_include_functions_once_and_inside_block() -> None:
    cd = "application simpleFoam;\nfunctions\n{\n    a { type Q; }\n}\n"
    once = P.include_functions(cd)
    assert once.index('#include "foamstudioFunctions"') > once.index("functions")
    assert P.include_functions(once) == once
    assert "functions\n{" in P.include_functions("application x;\n")


def test_unknown_inputs_raise() -> None:
    with pytest.raises(ValueError):
        P.turbulence("magic")
    with pytest.raises(ValueError):
        P.function_objects(["nope"])


def test_studies() -> None:
    pt = S.pump_point(1.75e7, 1500, 35000, 0.124, 805)
    assert abs(pt["H"] - 1.75e7 / (805 * 9.80665)) < 1e-6 and 0 < pt["eta"] < 1
    plan = S.latin_hypercube({"a": (0, 1), "b": (10, 20)}, 8)
    assert len(plan) == 8 and sorted(int(p["a"] * 8) for p in plan) == list(range(8))
    best, val = S.nelder_mead(
        lambda x: (x[0] - 3) ** 2 + (x[1] + 1) ** 2, [0.0, 0.0], step=1.0, iters=200
    )
    assert abs(best[0] - 3) < 1e-2 and abs(best[1] + 1) < 1e-2 and val < 1e-3
    f = S.response_surface([{"x": x} for x in range(5)], [x * x for x in range(5)])
    assert abs(f({"x": 2.5}) - 6.25) < 1e-9
    assert (
        abs(S.npsh_required([(10, 100), (6, 99), (4, 96), (2, 80)]) - 14 / 3) < 1e-9
    )  # H=97 between (6,99) and (4,96)
    t = [i / 1000 for i in range(1000)]
    f_, spl = S.spl_spectrum(t, [math.sin(2 * math.pi * 100 * x) for x in t])
    assert abs(f_[spl.argmax()] - 100) < 2
    p, ext, g = P.gci(0.99903, 0.99821, 0.99600)
    assert p > 0 and g > 0 and ext > 0.999

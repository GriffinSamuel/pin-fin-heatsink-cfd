"""T1 acceptance tests: three variants build, STLs are watertight, pin count and
solid volume match hand-derived values within 1%."""
import math
import os
import sys

import pytest
import trimesh

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.geometry import HeatSinkSpec, export_all, pin_positions  # noqa: E402

# Hand-derived expectations (base 60x60x4 mm, margin 1.5 mm):
#  d=2, p=3.6: usable 55 -> 16 per row, inline 16x16 = 256
#  d=3, p=6.6: usable 54 -> 9 per row; staggered rows alternate 9,8 -> 5*9 + 4*8 = 77
#  d=4, p=11.2: usable 53 -> 5 per row, inline 5x5 = 25
CASES = [
    (HeatSinkSpec(2, 1.8, 20, "inline"), 256),
    (HeatSinkSpec(3, 2.2, 35, "staggered"), 77),
    (HeatSinkSpec(4, 2.8, 20, "inline"), 25),
]


@pytest.mark.parametrize("spec,n_expected", CASES)
def test_pin_count(spec, n_expected):
    pos = pin_positions(spec)
    assert len(pos) == n_expected
    # every pin fully inside the base with the 1.5 mm margin
    for x, y in pos:
        assert 1.5 - 1e-6 <= x - spec.d / 2 and x + spec.d / 2 <= 58.5 + 1e-6
        assert 1.5 - 1e-6 <= y - spec.d / 2 and y + spec.d / 2 <= 58.5 + 1e-6
    # no two pins overlap
    for i in range(len(pos)):
        for j in range(i + 1, len(pos)):
            dist = math.dist(pos[i], pos[j])
            assert dist >= spec.d - 1e-6


@pytest.mark.parametrize("spec,n_expected", CASES)
def test_build_volume_and_watertight(spec, n_expected, tmp_path):
    meta = export_all(spec, str(tmp_path))
    v_hand = 60 * 60 * 4 + n_expected * math.pi * spec.d ** 2 / 4 * spec.h
    assert abs(meta["cad_volume_mm3"] - v_hand) / v_hand < 0.01
    for name in ("heatsink.stl", "heatsink_snappy.stl"):
        m = trimesh.load(str(tmp_path / name), force="mesh")
        assert m.is_watertight, f"{name} not watertight"
        assert m.is_winding_consistent
    assert (tmp_path / "heatsink.step").stat().st_size > 10_000
    # snappy STL is in metres and extends 1 mm outside the domain
    s = trimesh.load(str(tmp_path / "heatsink_snappy.stl"), force="mesh")
    lo, hi = s.bounds
    assert abs(lo[2] - (-0.001)) < 1e-6 and abs(lo[1] - (-0.001)) < 1e-6
    assert abs(hi[2] - (4 + spec.h + 1) * 1e-3) < 1e-6
    assert abs(hi[0] - 0.060) < 1e-6

"""T2 acceptance tests for the hand-calculation model."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.analytic import air_props, solve, spreading_resistance_lee, xi_gaddis_gnielinski  # noqa: E402
from src.geometry import HeatSinkSpec, metadata  # noqa: E402

CENTER = HeatSinkSpec(3, 2.2, 35, "staggered")


def test_air_properties_are_sane():
    p = air_props(25.0)
    assert abs(p["rho"] - 1.184) < 0.02
    assert abs(p["mu"] - 1.84e-5) < 0.05e-5
    assert abs(p["k"] - 0.0262) < 0.001
    assert 0.69 < p["Pr"] < 0.72


def test_center_design_plausible_and_monotonic():
    meta = metadata(CENTER)
    res = [solve(meta, V) for V in (2.0, 4.0, 6.0)]
    for r in res:
        assert 0.2 < r["R_total_K_W"] < 2.0, r
        assert 5 < r["dP_Pa"] < 500, r
        assert 0 < r["eta_fin"] < 1
        assert r["T_out"] > 25 and r["T_chip_max_C"] > r["T_fin_root_C"] > r["T_out"]
    assert res[0]["R_total_K_W"] > res[1]["R_total_K_W"] > res[2]["R_total_K_W"]
    assert res[0]["dP_Pa"] < res[1]["dP_Pa"] < res[2]["dP_Pa"]
    # the two Nu correlations should agree to within ~35 % (literature scatter)
    for r in res:
        assert abs(r["R_total_zukauskas_K_W"] - r["R_total_K_W"]) / r["R_total_K_W"] < 0.35


def test_energy_balance_consistency():
    meta = metadata(CENTER)
    r = solve(meta, 4.0)
    # heat removed = m_dot cp (T_out - T_in) must equal Q = 100 W by construction
    assert abs(r["m_dot_kg_s"] * 1006.0 * (r["T_out"] - 25.0) - 100.0) < 0.5


def test_spreading_limits():
    # source = plate: pure 1-D conduction t/(k A)
    k, t, A = 200.0, 0.004, 0.0036
    r = spreading_resistance_lee(A, A, t, k, 1000.0)
    assert abs(r - t / (k * A)) / (t / (k * A)) < 0.02
    # a smaller source must have a larger resistance
    assert spreading_resistance_lee(0.0009, A, t, k, 1000.0) > r


def test_gaddis_gnielinski_regimes():
    # laminar limit scales ~1/Re; turbulent part dominates at high Re
    lo = xi_gaddis_gnielinski(10, 2.2, 2.2, 9, True)
    hi = xi_gaddis_gnielinski(1e4, 2.2, 2.2, 9, True)
    assert lo > hi > 0
    # tighter pitch -> larger drag coefficient
    assert xi_gaddis_gnielinski(1500, 1.8, 1.8, 9, False) > xi_gaddis_gnielinski(1500, 2.8, 2.8, 9, False)

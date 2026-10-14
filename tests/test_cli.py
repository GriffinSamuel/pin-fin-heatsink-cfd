"""Tests for src/run.py that need no mesher (PLAN_CAD.md test 8)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import run  # noqa: E402
from src.geometry import PlateFinSpec, export_platefin  # noqa: E402


@pytest.fixture(scope="module")
def plate_step(tmp_path_factory):
    d = tmp_path_factory.mktemp("plate_cli")
    export_platefin(PlateFinSpec(1.5, 9, 35), str(d))
    return str(d / "heatsink.step")


def test_cli_dry_run(plate_step, tmp_path):
    out = str(tmp_path / "o")
    rc = run.main(["--cad", plate_step, "--chip", "30x30", "--power", "100", "--dry-run", "--out", out])
    assert rc == 0
    case = os.path.join(out, "heatsink_V4_coarse")
    meta = json.load(open(os.path.join(case, "case.json")))
    assert meta["kind"] == "cad"
    assert meta["q_flux_W_m2"] == pytest.approx(100 / 0.0009, rel=1e-6)
    assert meta["n_pins"] == 9 and meta["analytic"] == {}
    for f in ("system/fluid/blockMeshDict", "system/solid/snappyHexMeshDict", "constant/geometry/heatsink.stl", "Allmesh"):
        assert os.path.exists(os.path.join(case, f)), f


def test_cli_dry_run_copper_offset_two_speeds(plate_step, tmp_path):
    out = str(tmp_path / "o")
    rc = run.main(["--cad", plate_step, "--chip", "20x10", "--chip-offset", "5,-3", "--power", "50",
                   "--material", "copper", "--V", "2", "--V", "6", "--dry-run", "--out", out])
    assert rc == 0
    for v in (2, 6):
        meta = json.load(open(os.path.join(out, f"heatsink_V{v}_coarse", "case.json")))
        assert meta["kappa_solid"] == 385.0 and meta["power_W"] == 50
        assert meta["q_flux_W_m2"] == pytest.approx(50 / (0.020 * 0.010), rel=1e-6)
        assert meta["chip_m"] == pytest.approx([0.025, 0.022, 0.045, 0.032], abs=1e-5)


def test_cli_refusals_exit_2(plate_step, tmp_path, capsys):
    assert run.main(["--cad", str(tmp_path / "nope.step"), "--out", str(tmp_path / "o")]) == 2
    assert run.main(["--cad", plate_step, "--chip", "80x30", "--dry-run", "--out", str(tmp_path / "o2")]) == 2
    assert "does not fit" in capsys.readouterr().err
    assert run.main(["--cad", plate_step, "--chip", "abc", "--dry-run", "--out", str(tmp_path / "o3")]) == 2


def test_cli_inspect(plate_step, tmp_path, capsys):
    assert run.main(["--inspect", plate_step, "--out", str(tmp_path)]) == 0
    assert (tmp_path / "heatsink_inspect.png").exists()
    assert "fin height" in capsys.readouterr().out


def test_pareto_helper():
    rows = [dict(status="ok", V=4, R_max_K_W=r, dP_Pa=p) for r, p in [(0.4, 30), (0.3, 100), (0.35, 200), (0.5, 20)]]
    front = run.pareto(rows)
    assert [(r["R_max_K_W"], r["dP_Pa"]) for r in front] == [(0.5, 20), (0.4, 30), (0.3, 100)]


def test_summary_files(tmp_path):
    rows = [dict(name=f"s{i}_V4_coarse", file=f"s{i}.step", V=4.0, mesh="coarse", status="ok", n_fins=9, fin_mass_g=70.0,
                 R_max_K_W=r, T_solid_max_K=330.0, dP_Pa=p, Q_chip_W=100.0, interface_balance_err_pct=0.01,
                 cells_fluid=1, cells_solid=1, iterations=600, wall_s=1.0, warnings="rotated 90 degrees about z")
            for i, (r, p) in enumerate([(0.4, 30), (0.3, 100), (0.5, 20)])]
    run.write_summary(str(tmp_path), rows, "t")
    for f in ("sweep.csv", "pareto.csv", "pareto.png", "results.md"):
        assert (tmp_path / f).exists()
    md = (tmp_path / "results.md").read_text()
    assert "No hand calculation exists" in md and "rotated 90 degrees" in md


def test_cli_folder_dry_run_with_a_refused_file(plate_step, tmp_path, capsys):
    import shutil
    d = tmp_path / "sinks"
    d.mkdir()
    shutil.copy(plate_step, d / "plate.step")
    (d / "bad.stl").write_text("solid x\nendsolid x\n")
    rc = run.main(["--cad-dir", str(d), "--dry-run", "--out", str(tmp_path / "o")])
    assert rc == 2
    assert os.path.exists(tmp_path / "o" / "plate_V4_coarse" / "case.json")
    assert "refused bad.stl" in capsys.readouterr().out

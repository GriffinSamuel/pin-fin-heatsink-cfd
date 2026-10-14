"""Mesher checks for imported CAD (PLAN_CAD.md step 3). They need OpenFOAM v1912 (ESI) in the cloud workspace
and take minutes; run with  pytest --slow tests/test_cad_mesh.py"""
import os
import re
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import cad_import as ci  # noqa: E402
from src import make_case as mc  # noqa: E402
from src.geometry import HeatSinkSpec, PlateFinSpec, export_all, export_platefin  # noqa: E402

pytestmark = pytest.mark.slow

# parametric centre design, esi mesher, coarse (recorded 2026-10-14): the imported STEP must land within 3 %
PAR_FLUID, PAR_SOLID = 424552, 64132


def mesh(case):
    r = subprocess.run(["bash", "-c", f"source /usr/share/openfoam/etc/bashrc >/dev/null 2>&1; bash {case}/Allmesh"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    out = {}
    for reg in ("fluid", "solid"):
        txt = open(f"{case}/log.checkMesh.{reg}").read()
        assert "Mesh OK" in txt, f"{reg}: checkMesh not OK"
        out[reg] = int(re.search(r"cells:\s+(\d+)", txt).group(1))
    return out


@pytest.mark.skipif(shutil.which("snappyHexMesh") is None, reason="no OpenFOAM mesher")
def test_imported_centre_design_matches_parametric_mesh(tmp_path):
    export_all(HeatSinkSpec(3, 2.2, 35, "staggered"), str(tmp_path / "in"))
    m = ci.load(str(tmp_path / "in" / "heatsink.step"), out_dir=str(tmp_path / "imp"))
    dom = mc.domain_from_model(m, (30, 30))
    mc.write_case_from_model(m, dom, 4.0, "coarse", str(tmp_path / "case"), flavour="esi")
    n = mesh(str(tmp_path / "case"))
    assert n["fluid"] == pytest.approx(PAR_FLUID, rel=0.03)
    assert n["solid"] == pytest.approx(PAR_SOLID, rel=0.03)


@pytest.mark.skipif(shutil.which("snappyHexMesh") is None, reason="no OpenFOAM mesher")
def test_imported_plate_fin_meshes(tmp_path):
    export_platefin(PlateFinSpec(1.5, 9, 35), str(tmp_path / "in"))
    m = ci.load(str(tmp_path / "in" / "heatsink.step"), out_dir=str(tmp_path / "imp"))
    dom = mc.domain_from_model(m, (30, 30))
    mc.write_case_from_model(m, dom, 4.0, "coarse", str(tmp_path / "case"), flavour="esi")
    n = mesh(str(tmp_path / "case"))
    assert n["fluid"] > 100_000 and n["solid"] > 20_000

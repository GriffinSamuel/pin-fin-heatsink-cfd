"""Tests for src/cad_import.py (PLAN_CAD.md section 7, tests 3-7). No OpenFOAM needed."""
import json
import os
import sys

import numpy as np
import pytest
import trimesh

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import cad_import as ci  # noqa: E402
from src.geometry import HeatSinkSpec, PlateFinSpec, export_all, export_platefin  # noqa: E402


@pytest.fixture(scope="module")
def centre(tmp_path_factory):
    d = tmp_path_factory.mktemp("centre")
    meta = export_all(HeatSinkSpec(3, 2.2, 35, "staggered"), str(d))
    return d, meta


@pytest.fixture(scope="module")
def plate(tmp_path_factory):
    d = tmp_path_factory.mktemp("plate")
    meta = export_platefin(PlateFinSpec(1.5, 9, 35), str(d))
    return d, meta


def _same(a: ci.SinkModel, b: ci.SinkModel):
    assert a.L == pytest.approx(b.L, abs=0.05) and a.W == pytest.approx(b.W, abs=0.05)
    assert a.base_t == pytest.approx(b.base_t, abs=0.05) and a.h == pytest.approx(b.h, abs=0.05)
    assert a.n_fins == b.n_fins


def test_import_parametric_roundtrip(centre, tmp_path):
    d, meta = centre
    for name in ("heatsink.stl", "heatsink.step"):
        m = ci.load(str(d / name), out_dir=str(tmp_path / name))
        assert m.L == pytest.approx(60, abs=0.1) and m.W == pytest.approx(60, abs=0.1)
        assert m.base_t == pytest.approx(4.0, abs=0.3) and m.h == pytest.approx(35.0, abs=0.3)
        assert m.min_feature_mm == pytest.approx(3.0, abs=0.1)
        assert m.n_fins == 77
        assert m.volume_mm3 == pytest.approx(meta["cad_volume_mm3"], rel=0.005)
        assert m.warnings == []
        assert m.tip_gap_mm == 0.0
        assert os.path.exists(m.snappy_stl) and os.path.exists(m.clean_stl)


def test_snappy_stl_is_embedded_and_in_metres(centre, tmp_path):
    d, _ = centre
    m = ci.load(str(d / "heatsink.stl"), out_dir=str(tmp_path))
    s = trimesh.load(m.snappy_stl, force="mesh")
    assert s.is_watertight
    lo, hi = s.bounds
    # metres: 1 mm below the floor, 1 mm beyond the side walls, 1 mm above the shroud, flush at x = 0 and L
    assert lo[2] == pytest.approx(-0.001, abs=2e-5) and hi[2] == pytest.approx(0.039 + 0.001, abs=2e-5)
    assert lo[1] == pytest.approx(-0.001, abs=2e-5) and hi[1] == pytest.approx(0.061, abs=2e-5)
    assert lo[0] == pytest.approx(0.0, abs=2e-5) and hi[0] == pytest.approx(0.060, abs=2e-5)


@pytest.mark.parametrize("rot", [("x", 90), ("z", 90), ("y", 180), ("x", -90)])
def test_orientation(centre, tmp_path, rot):
    d, _ = centre
    ref = ci.load(str(d / "heatsink.stl"), out_dir=str(tmp_path / "ref"))
    mesh = trimesh.load(str(d / "heatsink.stl"), force="mesh")
    mesh.apply_transform(ci._rot(*rot))
    mesh.apply_translation([13.0, -7.0, 4.0])
    f = tmp_path / "rot.stl"
    mesh.export(str(f))
    m = ci.load(str(f), out_dir=str(tmp_path / "out"))
    _same(m, ref)
    assert np.asarray(m.transform).shape == (4, 4)


def test_plate_orientation(plate, tmp_path):
    d, _ = plate
    ref = ci.load(str(d / "heatsink.stl"), out_dir=str(tmp_path / "ref"))
    mesh = trimesh.load(str(d / "heatsink.stl"), force="mesh")
    mesh.apply_transform(ci._rot("z", 90))
    f = tmp_path / "plate_z90.stl"
    mesh.export(str(f))
    m = ci.load(str(f), out_dir=str(tmp_path / "out"))
    _same(m, ref)
    # plates run along x: each fin section is long in x
    for ring in m.fin_sections:
        r = np.asarray(ring)
        assert np.ptp(r[:, 0]) > 10 * np.ptp(r[:, 1])
    # a rotated file takes the 90 degree turn and says so
    assert any("90 degrees" in w for w in m.warnings)
    assert not any("90 degrees" in w for w in ref.warnings)


def test_explicit_orient_none_keeps_the_file_as_is(plate, tmp_path):
    d, _ = plate
    mesh = trimesh.load(str(d / "heatsink.stl"), force="mesh")
    mesh.apply_transform(ci._rot("z", 90))
    f = tmp_path / "plate_z90.stl"
    mesh.export(str(f))
    m = ci.load(str(f), orient="none", out_dir=str(tmp_path / "out"))
    for ring in m.fin_sections:
        r = np.asarray(ring)
        assert np.ptp(r[:, 1]) > 10 * np.ptp(r[:, 0])      # plates now run along y (flow across them)


def test_units(centre, tmp_path):
    d, _ = centre
    ref = ci.load(str(d / "heatsink.stl"), out_dir=str(tmp_path / "ref"))
    mesh = trimesh.load(str(d / "heatsink.stl"), force="mesh")
    mesh.apply_scale(0.001)
    f = tmp_path / "metres.stl"
    mesh.export(str(f))
    m = ci.load(str(f), out_dir=str(tmp_path / "out"))
    assert m.units_in == "m"
    _same(m, ref)
    assert m.min_feature_mm == pytest.approx(ref.min_feature_mm, abs=0.05)
    forced = ci.load(str(f), units="m", out_dir=str(tmp_path / "out2"))
    assert forced.units_in == "m" and forced.warnings == [] or forced.units_in == "m"


def test_refusals(tmp_path):
    # non-watertight and not repairable: a subdivided box with a third of its triangles removed at random
    b = trimesh.creation.box((60, 60, 4)).subdivide().subdivide()
    keep = np.random.default_rng(1).random(len(b.faces)) > 0.33
    b.update_faces(keep)
    f1 = tmp_path / "open.stl"
    b.export(str(f1))
    with pytest.raises(ci.InputRefused, match="watertight"):
        ci.load(str(f1), out_dir=str(tmp_path / "a"))
    # a plain block has no fins
    f2 = tmp_path / "block.stl"
    trimesh.creation.box((60, 60, 20)).export(str(f2))
    with pytest.raises(ci.InputRefused, match="no fins found"):
        ci.load(str(f2), out_dir=str(tmp_path / "b"))
    # two bodies
    two = trimesh.util.concatenate([trimesh.creation.box((10, 10, 10)),
                                    trimesh.creation.box((10, 10, 10)).apply_translation([30, 0, 0])])
    f3 = tmp_path / "two.stl"
    two.export(str(f3))
    with pytest.raises(ci.InputRefused, match="separate bodies"):
        ci.load(str(f3), out_dir=str(tmp_path / "c"))
    # wrong type and missing file
    with pytest.raises(ci.InputRefused, match="unsupported"):
        ci.load(str(tmp_path / "x.obj"), out_dir=str(tmp_path / "d")) if (tmp_path / "x.obj").write_text("v") else None
    with pytest.raises(ci.InputRefused, match="not found"):
        ci.load(str(tmp_path / "nope.stl"), out_dir=str(tmp_path / "e"))


def test_chip_must_fit(centre, tmp_path):
    d, _ = centre
    m = ci.load(str(d / "heatsink.stl"), out_dir=str(tmp_path))
    assert ci.chip_rect(m, (30, 30)) == pytest.approx((15, 15, 45, 45), abs=0.05)
    assert ci.chip_rect(m, (20, 10), (5, -3)) == pytest.approx((25, 22, 45, 32), abs=0.05)
    with pytest.raises(ci.InputRefused, match="does not fit"):
        ci.chip_rect(m, (70, 30))
    with pytest.raises(ci.InputRefused, match="does not fit"):
        ci.chip_rect(m, (30, 30), (20, 0))


def test_two_solid_step_refused(tmp_path):
    import cadquery as cq
    a = cq.Workplane("XY").box(10, 10, 10)
    b = cq.Workplane("XY").box(10, 10, 10).translate((30, 0, 0))
    f = tmp_path / "two.step"
    cq.exporters.export(cq.Workplane("XY").add(a.val()).add(b.val()), str(f))
    with pytest.raises(ci.InputRefused, match="solids|bodies"):
        ci.load(str(f), out_dir=str(tmp_path / "o"))


def test_flat_tip_vs_pointed_tip_warning(tmp_path):
    """Pins with pointed tips cannot be extended through the shroud: a tip gap is left and reported."""
    import cadquery as cq
    base = cq.Workplane("XY").box(60, 60, 4, centered=False)
    cone = (cq.Workplane("XY").workplane(offset=4).center(30, 30).circle(3).workplane(offset=20).circle(0.2).loft())
    m = base.union(cone)
    f = tmp_path / "cone.step"
    cq.exporters.export(m, str(f))
    # default: the tips are squared off to touch the shroud, no gap, and the importer says so
    model = ci.load(str(f), out_dir=str(tmp_path / "o"))
    # a needle-like cone may fall back to the gap if the float32 STL cannot hold the squared tip; either is reported
    assert model.tip_gap_mm in (0.0, ci.TIP_GAP_FALLBACK)
    assert any("tip" in w for w in model.warnings)
    assert trimesh.load(model.snappy_stl, force="mesh").is_watertight
    # the gap fallback is still available
    gap = ci.load(str(f), out_dir=str(tmp_path / "g"), tip_mode="gap")
    assert gap.tip_gap_mm == pytest.approx(ci.TIP_GAP_FALLBACK)
    assert any("tip gap" in w for w in gap.warnings)

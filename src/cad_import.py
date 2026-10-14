"""Import a heat sink from a STEP or STL file (PLAN_CAD.md section 2).

The importer turns an arbitrary single-body heat sink (flat base plate with fins standing on it)
into the frame the case generator expects:

    x = flow direction, y = span, z = up; base occupies x in [0, L], y in [0, W], z in [0, base_t];
    fins stand on the base top and end at z = base_t + h (the shroud touches the fin tips).

It measures the part (base thickness, fin height, thinnest feature, volume, area) and writes two STLs:

    <out_dir>/<stem>_clean.stl   oriented sink in mm (deliverable, renders)
    <out_dir>/<stem>_snappy.stl  same solid in METRES, extended 1 mm below the floor, 1 mm beyond the
                                 duct side walls and 1 mm above the shroud, so no STL face lies on a
                                 blockMesh boundary (what geometry.make_heatsink_for_snappy does for the
                                 parametric designs).

Nothing here touches OpenFOAM. Failures that would make the mesh meaningless raise InputRefused with a
message that says what to do about it.
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field

import numpy as np
import trimesh
from shapely.geometry import MultiPolygon, Polygon, box as shp_box
from shapely.ops import unary_union
from shapely.strtree import STRtree

EMBED = 1.0          # mm, same as src.geometry.EMBED
Z_STEP = 0.25        # mm, spacing of the sections used to find the base thickness
Z_EPS = 0.0013       # mm, keeps section planes off coincident faces
BASE_DROP = 0.6      # section area must fall below this fraction of the base area to count as "fins"
TIP_GAP_FALLBACK = 0.3   # mm, shroud clearance used when the fin tips are not flat


class InputRefused(Exception):
    """The input file cannot be used; the message says why and what to do."""


@dataclass
class SinkModel:
    source: str
    units_in: str
    transform: list
    L: float
    W: float
    base_t: float
    h: float
    footprint: list
    fin_sections: list
    min_feature_mm: float
    min_thickness_mm: float
    min_gap_mm: float | None
    volume_mm3: float
    fin_volume_mm3: float
    wetted_area_mm2: float
    n_fins: int
    clean_stl: str
    snappy_stl: str
    tip_gap_mm: float = 0.0
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("footprint"), d.pop("fin_sections")        # large; the figure redraws them
        return d


# ------------------------------------------------------------------ helpers

def _polys_from_section(mesh: trimesh.Trimesh, z: float):
    """Cross-section of the mesh at height z as a shapely geometry (even-odd rule for holes)."""
    path = mesh.section(plane_origin=[0.0, 0.0, z], plane_normal=[0.0, 0.0, 1.0])
    if path is None:
        return Polygon()
    rings = [Polygon(np.asarray(r)[:, :2]).buffer(0) for r in path.discrete if len(r) >= 4]
    rings = [r for r in rings if not r.is_empty]
    rings.sort(key=lambda p: -p.area)
    geom = Polygon()
    for r in rings:
        geom = geom.symmetric_difference(r)
    return geom


def _parts(geom) -> list[Polygon]:
    if geom.is_empty:
        return []
    return list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]


def _apply(mesh: trimesh.Trimesh, T: np.ndarray, total: np.ndarray) -> np.ndarray:
    mesh.apply_transform(T)
    return T @ total


def _rot(axis: str, deg: float) -> np.ndarray:
    a = math.radians(deg)
    return trimesh.transformations.rotation_matrix(a, {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}[axis])


def _shift_to_origin(mesh: trimesh.Trimesh, total: np.ndarray, xy: bool = True) -> np.ndarray:
    lo = mesh.bounds[0].copy()
    if not xy:
        lo[:2] = 0.0
    return _apply(mesh, trimesh.transformations.translation_matrix(-lo), total)


# ------------------------------------------------------------------ loading

def _load_mesh(path: str) -> trimesh.Trimesh:
    ext = os.path.splitext(path)[1].lower()
    if not os.path.exists(path):
        raise InputRefused(f"{path}: file not found")
    if ext in (".step", ".stp"):
        import cadquery as cq
        wp = cq.importers.importStep(path)
        solids = wp.solids().vals()
        if len(solids) != 1:
            raise InputRefused(f"{path}: file contains {len(solids)} solids; export the heat sink as one body "
                               "(union the base and fins in your CAD tool first)")
        with tempfile.TemporaryDirectory() as td:
            tmp = os.path.join(td, "tess.stl")
            cq.exporters.export(wp, tmp, tolerance=0.02, angularTolerance=0.1)
            mesh = trimesh.load(tmp, force="mesh")
    elif ext == ".stl":
        mesh = trimesh.load(path, force="mesh")
    else:
        raise InputRefused(f"{path}: unsupported file type {ext!r}; use .step, .stp or .stl")
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise InputRefused(f"{path}: no triangles found")
    mesh.merge_vertices()
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    if not mesh.is_watertight:
        trimesh.repair.fix_normals(mesh)
        trimesh.repair.fill_holes(mesh)
    if not mesh.is_watertight:
        n_open = len(mesh.facets_boundary) if hasattr(mesh, "facets_boundary") else -1
        edges = trimesh.grouping.group_rows(mesh.edges_sorted, require_count=1)
        raise InputRefused(f"{path}: the surface is not watertight ({len(edges)} open edges"
                           f"{f', {n_open} open loops' if n_open >= 0 else ''}); repair it in your CAD tool "
                           "(or re-export the STEP with a finer tolerance) and try again")
    if mesh.volume < 0:
        mesh.invert()
    bodies = mesh.split(only_watertight=False)
    if len(bodies) > 1:
        raise InputRefused(f"{path}: the file holds {len(bodies)} separate bodies; export one connected heat sink")
    return mesh


# ------------------------------------------------------------------ units and orientation

def _detect_units(mesh: trimesh.Trimesh, units: str, warnings: list[str], path: str) -> tuple[str, float]:
    if units == "mm":
        return "mm", 1.0
    if units == "m":
        return "m", 1000.0
    if units == "in":
        return "in", 25.4
    e = float(np.max(mesh.extents))
    if e < 1.0:
        warnings.append(f"largest extent {e:.4g} looks like metres; scaled by 1000 (override with --units)")
        return "m", 1000.0
    if e > 2000.0:
        raise InputRefused(f"{path}: largest extent is {e:.4g}; that is not a heat sink in mm. "
                           "Pass --units m or --units in if the file uses other units")
    if e < 10.0:
        warnings.append(f"largest extent is only {e:.3g} mm; if the file is in inches pass --units in")
    return "mm", 1.0


def _auto_up(mesh: trimesh.Trimesh, total: np.ndarray) -> np.ndarray:
    """Rotate so the largest flat face (the base bottom) points to -z. Ties: prefer the candidate
    with more triangles in the upper half of the part (that is where the fins are)."""
    if len(mesh.facets) == 0:
        raise InputRefused("no flat faces found, cannot tell which side is the base; pass --orient")
    areas = mesh.facets_area
    order = np.argsort(-areas)
    cands = [i for i in order if areas[i] >= 0.98 * areas[order[0]]]
    best, best_score = None, -1
    for i in cands[:6]:
        n = mesh.facets_normal[i]
        M = trimesh.geometry.align_vectors(n, [0.0, 0.0, -1.0])
        pts = (M[:3, :3] @ mesh.triangles_center.T).T + M[:3, 3]
        z = pts[:, 2]
        score = int(np.sum(z > z.min() + 0.5 * (z.max() - z.min())))
        if score > best_score:
            best, best_score = M, score
    return _apply(mesh, best, total)


def _fin_normals_xy(mesh: trimesh.Trimesh, base_t: float) -> tuple[float, float]:
    sel = mesh.triangles_center[:, 2] > base_t + 0.01
    n, a = mesh.face_normals[sel], mesh.area_faces[sel]
    return float(np.sum(np.abs(n[:, 0]) * a)), float(np.sum(np.abs(n[:, 1]) * a))


def _find_base_t(mesh: trimesh.Trimesh) -> tuple[float, float]:
    """Base thickness and fin height from cross-section areas."""
    zmax = float(mesh.bounds[1][2])
    a0 = _polys_from_section(mesh, Z_STEP + Z_EPS).area
    if a0 <= 0:
        raise InputRefused("could not section the part just above its bottom face; the model may be inverted")
    lo, hi, z = None, None, Z_STEP + Z_EPS
    prev = z
    while z < zmax - 0.05:
        if _polys_from_section(mesh, z).area < BASE_DROP * a0:
            lo, hi = prev, z
            break
        prev, z = z, z + Z_STEP
    if hi is None:
        raise InputRefused("no fins found above the base: the cross-section never narrows. "
                           "Check that the file is a heat sink and that it is oriented with the fins away from the "
                           "flat base (--orient)")
    for _ in range(12):
        mid = 0.5 * (lo + hi)
        if _polys_from_section(mesh, mid).area < BASE_DROP * a0:
            hi = mid
        else:
            lo = mid
    base_t = 0.5 * (lo + hi)
    return base_t, zmax - base_t


# ------------------------------------------------------------------ measurements

def _min_feature(parts: list[Polygon]) -> tuple[float, float | None, float]:
    """(min feature, min gap or None, min thickness). Thickness is the short side of each fin's minimum
    rotated rectangle (exact for pins and straight plates, approximate for other shapes)."""
    thick = []
    for p in parts:
        r = p.minimum_rotated_rectangle
        if r.geom_type != "Polygon":
            continue
        c = np.asarray(r.exterior.coords)
        s = sorted([np.linalg.norm(c[1] - c[0]), np.linalg.norm(c[2] - c[1])])
        thick.append(s[0])
    t_min = float(min(thick)) if thick else float("inf")
    gap = None
    if len(parts) > 1:
        tree = STRtree(parts)
        idx, dist = tree.query_nearest(parts, return_distance=True, exclusive=True, all_matches=False)
        gap = float(np.min(dist)) if len(dist) else None
    elif len(parts) == 1:
        import shapely
        mc = shapely.minimum_clearance(parts[0])
        gap = float(mc) if np.isfinite(mc) else None
    feat = min(x for x in (t_min, gap if gap is not None else float("inf")))
    return float(feat), gap, t_min


def _fin_volume(mesh: trimesh.Trimesh, base_t: float) -> float:
    ext = mesh.extents
    cut = trimesh.creation.box(extents=(ext[0] + 4, ext[1] + 4, mesh.bounds[1][2] - base_t + 2.0))
    cut.apply_translation([mesh.centroid[0] * 0 + (mesh.bounds[0][0] + mesh.bounds[1][0]) / 2,
                           (mesh.bounds[0][1] + mesh.bounds[1][1]) / 2,
                           base_t + (mesh.bounds[1][2] - base_t + 2.0) / 2])
    part = trimesh.boolean.intersection([mesh, cut], engine="manifold")
    return float(abs(part.volume))


# ------------------------------------------------------------------ embedding

def _embed_for_snappy(mesh: trimesh.Trimesh, base_t: float, L: float, W: float, fin_area: float,
                      warnings: list[str]) -> tuple[trimesh.Trimesh, float]:
    """Return the sink extended so no face lies on a mesh boundary, plus the tip gap actually used (mm)."""
    zmax = float(mesh.bounds[1][2])
    parts = [mesh]
    # below the floor and beyond the side walls: footprint buffered by EMBED, kept inside x in [0, L]
    foot = _polys_from_section(mesh, base_t / 2.0)
    slab = foot.buffer(EMBED, join_style=2).intersection(shp_box(0.0, -EMBED, L, W + EMBED))
    for poly in _parts(slab):
        s = trimesh.creation.extrude_polygon(poly, height=base_t / 2.0 + EMBED)
        s.apply_translation([0.0, 0.0, -EMBED])
        parts.append(s)
    # above the shroud: caps over the flat fin tips
    sel = ((mesh.triangles_center[:, 2] > zmax - 0.05) & (mesh.face_normals[:, 2] > 0.99))
    tip_gap = 0.0
    # flat tips cover most of the fin cross-section; domes and points do not
    if np.any(sel) and float(mesh.area_faces[sel].sum()) >= 0.5 * fin_area:
        tris = [Polygon(t[:, :2]) for t in mesh.triangles[sel] if Polygon(t[:, :2]).area > 0]
        tips = unary_union(tris).buffer(0)
        for poly in _parts(tips):
            c = trimesh.creation.extrude_polygon(poly, height=0.5 + EMBED)
            c.apply_translation([0.0, 0.0, zmax - 0.5])
            parts.append(c)
    else:
        tip_gap = TIP_GAP_FALLBACK
        warnings.append(f"fin tips are not flat; a {TIP_GAP_FALLBACK} mm tip gap was left below the shroud "
                        "(the study's designs have none, so results differ slightly in physics)")
    out = trimesh.boolean.union(parts, engine="manifold")
    if not out.is_watertight:
        raise InputRefused("could not extend the model through the duct walls (the union is not watertight); "
                           "simplify the geometry near the base edges and fin tips")
    return out, tip_gap


# ------------------------------------------------------------------ public API

def load(path: str, units: str = "auto", orient: str = "auto", out_dir: str | None = None) -> SinkModel:
    """Load, orient, measure and embed a heat sink. orient: 'auto', 'none', or a rotation list such as
    'x90 z-90' (degrees about x then z, applied in order) in which case auto-detection is skipped."""
    warnings: list[str] = []
    mesh = _load_mesh(path)
    total = np.eye(4)
    u, scale = _detect_units(mesh, units, warnings, path)
    if scale != 1.0:
        total = _apply(mesh, np.diag([scale, scale, scale, 1.0]), total)

    if orient == "auto":
        total = _auto_up(mesh, total)
    elif orient != "none":
        for tok in orient.split():
            m = re.fullmatch(r"([xyz])(-?\d+(?:\.\d+)?)", tok)
            if not m:
                raise InputRefused(f"bad --orient token {tok!r}; use e.g. 'x90 z-90', 'none' or 'auto'")
            total = _apply(mesh, _rot(m.group(1), float(m.group(2))), total)
    total = _shift_to_origin(mesh, total, xy=True)

    base_t, h = _find_base_t(mesh)
    if orient == "auto":
        nx, ny = _fin_normals_xy(mesh, base_t)
        if nx > 1.05 * ny:                     # fin sides face the flow: turn the part 90 degrees about z
            total = _apply(mesh, _rot("z", 90.0), total)
            total = _shift_to_origin(mesh, total, xy=True)
            warnings.append("rotated 90 degrees about z so the fins run along the flow")
    L, W = float(mesh.extents[0]), float(mesh.extents[1])

    foot = _polys_from_section(mesh, base_t / 2.0)
    fins = _polys_from_section(mesh, base_t + h / 2.0)
    parts = _parts(fins)
    feat, gap, thick = _min_feature(parts)
    if min(L, W) < 5 * feat:
        warnings.append("the base is under 5 times the thinnest feature; check the units")
    if h < 3 * thick:
        warnings.append("fins are shorter than 3 times their thickness; the section-based measurements may be rough")
    fin_vol = _fin_volume(mesh, base_t)
    sel = mesh.triangles_center[:, 2] > base_t + 0.01
    wetted = float(mesh.area_faces[sel].sum())

    stem = os.path.splitext(os.path.basename(path))[0]
    out_dir = out_dir or os.path.join("work", "cad", stem)
    os.makedirs(out_dir, exist_ok=True)
    clean_stl = os.path.join(out_dir, f"{stem}_clean.stl")
    snappy_stl = os.path.join(out_dir, f"{stem}_snappy.stl")
    mesh.export(clean_stl)
    emb, tip_gap = _embed_for_snappy(mesh, base_t, L, W, float(fins.area), warnings)
    emb.apply_scale(0.001)
    emb.export(snappy_stl)

    model = SinkModel(
        source=os.path.abspath(path), units_in=u, transform=total.tolist(), L=L, W=W, base_t=base_t, h=h,
        footprint=[list(map(list, np.asarray(p.exterior.coords))) for p in _parts(foot)],
        fin_sections=[list(map(list, np.asarray(p.exterior.coords))) for p in parts],
        min_feature_mm=feat, min_thickness_mm=thick, min_gap_mm=gap, volume_mm3=float(mesh.volume),
        fin_volume_mm3=fin_vol, wetted_area_mm2=wetted, n_fins=len(parts), clean_stl=clean_stl,
        snappy_stl=snappy_stl, tip_gap_mm=tip_gap, warnings=warnings)
    with open(os.path.join(out_dir, f"{stem}_model.json"), "w") as f:
        json.dump(model.to_dict(), f, indent=2)
    return model


def chip_rect(model: SinkModel, size: tuple[float, float], offset: tuple[float, float] = (0.0, 0.0)
              ) -> tuple[float, float, float, float]:
    """Chip rectangle (x0, y0, x1, y1) in mm, centred on the base plus offset; refuses if it leaves the base."""
    cx, cy = model.L / 2 + offset[0], model.W / 2 + offset[1]
    x0, x1, y0, y1 = cx - size[0] / 2, cx + size[0] / 2, cy - size[1] / 2, cy + size[1] / 2
    if x0 < 0 or y0 < 0 or x1 > model.L or y1 > model.W:
        raise InputRefused(f"the {size[0]:g} x {size[1]:g} mm chip does not fit on the {model.L:.1f} x {model.W:.1f} mm "
                           "base at that offset; reduce --chip or --chip-offset")
    return x0, y0, x1, y1


def inspect_figure(model: SinkModel, png_path: str, chip: tuple[float, float, float, float] | None = None) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MplPoly, Rectangle

    fig, ax = plt.subplots(figsize=(6.4, 5.4))
    for ring in model.footprint:
        ax.add_patch(MplPoly(np.asarray(ring), closed=True, fill=False, ec="#5f666d", lw=1.2))
    for ring in model.fin_sections:
        ax.add_patch(MplPoly(np.asarray(ring), closed=True, fc="#1f6e8c", ec="none", alpha=0.85))
    if chip:
        ax.add_patch(Rectangle((chip[0], chip[1]), chip[2] - chip[0], chip[3] - chip[1], fill=False, ec="#c7441a",
                               lw=1.4, ls="--"))
    ax.annotate("", xy=(-4, model.W / 2), xytext=(-14, model.W / 2), arrowprops=dict(arrowstyle="-|>", color="#1b1f23"))
    ax.text(-14, model.W / 2 + 2, "air", fontsize=9)
    ax.set_xlim(-16, model.L + 6)
    ax.set_ylim(-6, model.W + 6)
    ax.set_aspect("equal")
    ax.set_xlabel("x, flow direction (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_title(f"{os.path.basename(model.source)}: base {model.L:.1f} x {model.W:.1f} x {model.base_t:.1f} mm, "
                 f"fins {model.h:.1f} mm tall\n{model.n_fins} fin section(s), thinnest feature {model.min_feature_mm:.2f} mm",
                 fontsize=9.5)
    fig.tight_layout()
    fig.savefig(png_path, dpi=130)
    plt.close(fig)
    return png_path


def describe(model: SinkModel) -> str:
    rows = [("source", os.path.basename(model.source)), ("units in file", model.units_in),
            ("base L x W x t (mm)", f"{model.L:.2f} x {model.W:.2f} x {model.base_t:.2f}"),
            ("fin height (mm)", f"{model.h:.2f}"), ("fin sections at mid-height", str(model.n_fins)),
            ("thinnest fin (mm)", f"{model.min_thickness_mm:.2f}"),
            ("narrowest gap (mm)", "n/a" if model.min_gap_mm is None else f"{model.min_gap_mm:.2f}"),
            ("metal volume (cm3)", f"{model.volume_mm3 / 1000:.2f}"), ("fin volume (cm3)", f"{model.fin_volume_mm3 / 1000:.2f}"),
            ("fin surface above base (cm2)", f"{model.wetted_area_mm2 / 100:.1f}")]
    out = "\n".join(f"{k:32s}{v}" for k, v in rows)
    if model.warnings:
        out += "\n" + "\n".join(f"warning: {w}" for w in model.warnings)
    return out

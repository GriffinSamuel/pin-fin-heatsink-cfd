"""Parametric pin-fin heat sink geometry (CadQuery).

Coordinate system (mm): x = flow direction, y = spanwise, z = up.
The base plate occupies x in [0, L], y in [0, W], z in [0, base_t].
Pins stand on the base top (z = base_t) with height h.
The chip footprint (heat source) is centered on the underside of the base.

Two STL flavours are exported:
  * heatsink.stl        clean solid in mm, for display / CAD deliverable (plus STEP)
  * heatsink_snappy.stl solid in METRES, extended 1 mm below the floor, 1 mm beyond the
                        duct side walls and 1 mm above the shroud, so that no STL face
                        coincides with a mesh boundary (snappyHexMesh cuts through it).
"""
from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass, asdict

import cadquery as cq

BASE_L = 60.0      # mm, streamwise length of the base plate
BASE_W = 60.0      # mm, spanwise width
BASE_T = 4.0       # mm, base thickness
CHIP = 30.0        # mm, square chip side
MARGIN = 1.5       # mm, min gap between pin edge and base edge
EMBED = 1.0        # mm, how far the snappy STL extends outside the domain
AL_DENSITY = 2700.0  # kg/m^3


@dataclass
class HeatSinkSpec:
    d: float            # pin diameter, mm
    pd: float           # pitch / diameter
    h: float            # pin height, mm
    layout: str         # "inline" or "staggered"
    base_l: float = BASE_L
    base_w: float = BASE_W
    base_t: float = BASE_T

    @property
    def pitch(self) -> float:
        return self.pd * self.d

    @property
    def name(self) -> str:
        return f"d{self.d:g}_pd{self.pd:g}_h{self.h:g}_{self.layout}"


def pin_positions(spec: HeatSinkSpec, margin: float = MARGIN) -> list[tuple[float, float]]:
    """Pin centre coordinates (x, y) in mm. Rows are lines of constant x (across the flow).
    Inline: square array with pitch p in both directions, centred on the base.
    Staggered: every other row (in x) is shifted by p/2 in y; pins that would then poke
    past the margin are dropped, so shifted rows have one pin fewer."""
    if spec.layout not in ("inline", "staggered"):
        raise ValueError(f"layout must be inline or staggered, got {spec.layout!r}")
    p, d = spec.pitch, spec.d
    xs = _centered_line(spec.base_l, p, d, margin)
    ys = _centered_line(spec.base_w, p, d, margin)
    pos = []
    for i, x in enumerate(xs):
        shift = p / 2 if (spec.layout == "staggered" and i % 2 == 1) else 0.0
        for y in ys:
            yy = y + shift
            if yy + d / 2 <= spec.base_w - margin + 1e-9:
                pos.append((round(x, 6), round(yy, 6)))
    return pos


def _centered_line(length: float, pitch: float, d: float, margin: float) -> list[float]:
    usable = length - 2 * margin - d
    n = int(math.floor(usable / pitch + 1e-9)) + 1
    span = (n - 1) * pitch
    x0 = (length - span) / 2
    return [x0 + i * pitch for i in range(n)]


def metadata(spec: HeatSinkSpec) -> dict:
    pos = pin_positions(spec)
    n = len(pos)
    rows = sorted({x for x, _ in pos})
    a_pin = math.pi * spec.d * spec.h                      # lateral area per pin, mm^2
    a_tip = math.pi * spec.d ** 2 / 4
    a_base_top = spec.base_l * spec.base_w - n * a_tip        # exposed base top
    v_pins = n * a_tip * spec.h
    v_base = spec.base_l * spec.base_w * spec.base_t
    return {
        "spec": asdict(spec),
        "pitch_mm": spec.pitch,
        "n_pins": n,
        "n_rows": len(rows),                                  # rows along the flow
        "pins_per_row_max": max(sum(1 for x, _ in pos if x == r) for r in rows),
        "pin_positions_mm": pos,
        "volume_mm3": v_base + v_pins,
        "fin_volume_mm3": v_pins,
        "fin_mass_g": v_pins * 1e-9 * AL_DENSITY * 1e3,
        "total_mass_g": (v_base + v_pins) * 1e-9 * AL_DENSITY * 1e3,
        "area_pins_mm2": n * (a_pin + a_tip),
        "area_base_exposed_mm2": a_base_top,
        "area_total_wetted_mm2": n * (a_pin + a_tip) + a_base_top,
        "chip_mm": CHIP,
        "chip_xy_mm": [(spec.base_l - CHIP) / 2, (spec.base_w - CHIP) / 2],
        "duct_height_mm": spec.base_t + spec.h,               # shroud touches the pin tips
    }


def make_heatsink(spec: HeatSinkSpec) -> cq.Workplane:
    """Clean solid: base plate + pins, in mm."""
    base = cq.Workplane("XY").box(spec.base_l, spec.base_w, spec.base_t, centered=False)
    pins = (cq.Workplane("XY").workplane(offset=spec.base_t)
            .pushPoints(pin_positions(spec)).circle(spec.d / 2).extrude(spec.h))
    return base.union(pins)


def make_heatsink_for_snappy(spec: HeatSinkSpec, embed: float = EMBED) -> cq.Workplane:
    """Same solid, extended outside the fluid domain so the mesh boundaries cut it:
    base extended below z=0 and beyond y=0 / y=W, pins extended above the shroud.
    The pins also start 1 mm inside the base so the STL is one clean union."""
    base = (cq.Workplane("XY")
            .box(spec.base_l, spec.base_w + 2 * embed, spec.base_t + embed, centered=False)
            .translate((0, -embed, -embed)))
    pins = (cq.Workplane("XY").workplane(offset=spec.base_t - 1.0)
            .pushPoints(pin_positions(spec)).circle(spec.d / 2).extrude(spec.h + 1.0 + embed))
    return base.union(pins)


def export_all(spec: HeatSinkSpec, out_dir: str, tol: float = 0.02) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    clean = make_heatsink(spec)
    snappy = make_heatsink_for_snappy(spec)
    cq.exporters.export(clean, os.path.join(out_dir, "heatsink.step"))
    cq.exporters.export(clean, os.path.join(out_dir, "heatsink.stl"), tolerance=tol, angularTolerance=0.1)
    snappy_m = snappy.val().scale(0.001)                      # metres for OpenFOAM
    cq.exporters.export(cq.Workplane("XY").add(snappy_m), os.path.join(out_dir, "heatsink_snappy.stl"),
                        tolerance=tol * 1e-3, angularTolerance=0.1)
    meta = metadata(spec)
    meta["cad_volume_mm3"] = clean.val().Volume()
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate pin-fin heat sink geometry")
    ap.add_argument("--d", type=float, required=True)
    ap.add_argument("--pd", type=float, required=True)
    ap.add_argument("--h", type=float, required=True)
    ap.add_argument("--layout", choices=["inline", "staggered"], required=True)
    ap.add_argument("--out", default=None, help="output dir (default work/geom/<name>)")
    a = ap.parse_args(argv)
    spec = HeatSinkSpec(a.d, a.pd, a.h, a.layout)
    out = a.out or os.path.join("work", "geom", spec.name)
    meta = export_all(spec, out)
    print(f"{spec.name}: {meta['n_pins']} pins, {meta['n_rows']} rows, "
          f"CAD volume {meta['cad_volume_mm3']:.1f} mm^3 (analytic {meta['volume_mm3']:.1f}), "
          f"fin mass {meta['fin_mass_g']:.1f} g -> {out}")


if __name__ == "__main__":
    main()

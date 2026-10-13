"""Headless renders of a finished case (T9) with pyvista/VTK (no ParaView GUI needed).

    xvfb-run -a .venv/bin/python -m src.visuals --case work/sweep/<case> --out figures/<name>

Produces: <name>_solid_T.png (solid surface temperature), <name>_slice_T.png (vertical mid-plane
temperature), <name>_slice_U.png (horizontal mid-height speed), <name>_streamlines.png,
<name>_p.png (static pressure on the mid-plane) and <name>_mesh.png (surface mesh close-up).
Fields are read at the latest time step. Single-hue sequential colormaps throughout.
"""
from __future__ import annotations

import argparse
import glob
import os

import numpy as np
import pyvista as pv

pv.OFF_SCREEN = True
BG = "#fcfcfb"
SOLID_GREY = "#b8b6ae"
T_IN = 298.15


def load_case(case: str):
    foam = os.path.join(case, "case.foam")
    open(foam, "a").close()
    r = pv.OpenFOAMReader(foam)
    times = list(r.time_values)
    if times:
        r.set_active_time_value(times[-1])
    r.enable_all_patch_arrays()
    r.cell_to_point_creation = True
    mb = r.read()
    regions = {}
    for i in range(mb.n_blocks):
        name = mb.get_block_name(i)
        blk = mb[i]
        if isinstance(blk, pv.MultiBlock) and blk.n_blocks and blk.get_block_name(0) == "internalMesh":
            regions[name] = blk
    return regions, times


def region(regions: dict, kind: str):
    for name, blk in regions.items():
        if kind == "solid" and name == "solid":
            return blk
        if kind == "fluid" and name not in ("solid", "defaultRegion"):
            return blk
    return None


def celsius(ds):
    if ds is not None and "T" in ds.point_data:
        ds.point_data["T_C"] = ds.point_data["T"] - 273.15
    if ds is not None and "T" in ds.cell_data:
        ds.cell_data["T_C"] = ds.cell_data["T"] - 273.15
    return ds


def plotter():
    p = pv.Plotter(off_screen=True, window_size=(1400, 900))
    p.set_background(BG)
    return p


def save(p: pv.Plotter, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    p.screenshot(path)
    p.close()


def render_all(case: str, out: str, name: str) -> list[str]:
    regions, times = load_case(case)
    solid = region(regions, "solid")
    fluid = region(regions, "fluid")
    made = []
    if solid is None or fluid is None:
        raise RuntimeError(f"regions not found: {list(regions)}")
    s_mesh = celsius(solid["internalMesh"])
    f_mesh = celsius(fluid["internalMesh"])
    s_surf = s_mesh.extract_surface()
    have_T = "T_C" in s_surf.point_data
    have_U = "U" in f_mesh.point_data
    have_p = "p" in f_mesh.point_data
    sargs = dict(title_font_size=18, label_font_size=14, color="#52514e", n_labels=5, fmt="%.0f", vertical=False,
                 position_x=0.25, position_y=0.05, width=0.5, height=0.06)

    # 1. solid temperature
    p = plotter()
    if have_T:
        p.add_mesh(s_surf, scalars="T_C", cmap="Oranges", scalar_bar_args={**sargs, "title": "Solid temperature, C"})
    else:
        p.add_mesh(s_surf, color=SOLID_GREY)
    p.camera_position = "iso"
    p.camera.azimuth = -150; p.camera.elevation = 20
    p.camera.zoom(1.15)
    path = os.path.join(out, f"{name}_solid_T.png"); save(p, path); made.append(path)

    # 2. vertical mid-plane (y = 30 mm) temperature of fluid + solid
    p = plotter()
    sl = f_mesh.slice(normal="y", origin=(0, 0.030, 0))
    ss = s_mesh.slice(normal="y", origin=(0, 0.030, 0))
    if have_T and "T_C" in sl.point_data:
        rng = [float(T_IN - 273.15), float(max(ss.point_data["T_C"].max(), sl.point_data["T_C"].max()))]
        p.add_mesh(sl, scalars="T_C", cmap="Oranges", clim=rng, scalar_bar_args={**sargs, "title": "Temperature, C"})
        p.add_mesh(ss, scalars="T_C", cmap="Oranges", clim=rng, show_scalar_bar=False)
    else:
        p.add_mesh(sl, color="#cde2fb"); p.add_mesh(ss, color=SOLID_GREY)
    p.view_xz(); p.camera.zoom(1.8)
    path = os.path.join(out, f"{name}_slice_T.png"); save(p, path); made.append(path)

    # 3. horizontal slice through the fins: speed
    zb = s_mesh.bounds
    z_mid = 0.004 + 0.5 * (zb[5] - 0.004)
    p = plotter()
    sl = f_mesh.slice(normal="z", origin=(0, 0, z_mid))
    if have_U:
        sl["speed"] = np.linalg.norm(sl.point_data["U"], axis=1)
        p.add_mesh(sl, scalars="speed", cmap="Blues", scalar_bar_args={**sargs, "title": "Speed, m/s", "fmt": "%.1f"})
    else:
        p.add_mesh(sl, color="#cde2fb")
    p.add_mesh(s_mesh.slice(normal="z", origin=(0, 0, z_mid)), color=SOLID_GREY)
    p.view_xy(); p.camera.zoom(1.8)
    path = os.path.join(out, f"{name}_slice_U.png"); save(p, path); made.append(path)

    # 4. streamlines seeded upstream of the heat sink
    p = plotter()
    if have_U:
        seeds = pv.Plane(center=(-0.020, 0.030, z_mid), direction=(1, 0, 0), i_size=0.058, j_size=zb[5] - 0.006,
                         i_resolution=12, j_resolution=6)
        try:
            stream = f_mesh.streamlines_from_source(seeds, vectors="U", max_time=0.5, integration_direction="forward")
            stream["speed"] = np.linalg.norm(stream.point_data["U"], axis=1)
            p.add_mesh(stream.tube(radius=0.0003), scalars="speed", cmap="Blues",
                       scalar_bar_args={**sargs, "title": "Speed, m/s", "fmt": "%.1f"})
        except Exception as e:  # streamlines can fail on odd meshes; keep the solid render
            print("streamlines failed:", e)
    p.add_mesh(s_surf, color=SOLID_GREY)
    p.camera_position = "iso"
    p.camera.azimuth = -150; p.camera.elevation = 25
    p.camera.zoom(1.1)
    path = os.path.join(out, f"{name}_streamlines.png"); save(p, path); made.append(path)

    # 5. static pressure on the vertical mid-plane, relative to the outlet
    p = plotter()
    sl = f_mesh.slice(normal="y", origin=(0, 0.030, 0))
    if have_p:
        sl["p_rel"] = sl.point_data["p"] - float(np.min(sl.point_data["p"]))
        p.add_mesh(sl, scalars="p_rel", cmap="Blues", scalar_bar_args={**sargs, "title": "Pressure above outlet, Pa"})
    else:
        p.add_mesh(sl, color="#cde2fb")
    p.add_mesh(s_mesh.slice(normal="y", origin=(0, 0.030, 0)), color=SOLID_GREY)
    p.view_xz(); p.camera.zoom(1.8)
    path = os.path.join(out, f"{name}_p.png"); save(p, path); made.append(path)

    # 6. mesh close-up on the fins (horizontal slice, edges shown)
    p = plotter()
    sl = f_mesh.slice(normal="z", origin=(0, 0, z_mid))
    p.add_mesh(sl, color="#e8f1fb", show_edges=True, edge_color="#898781", line_width=0.5)
    p.add_mesh(s_mesh.slice(normal="z", origin=(0, 0, z_mid)), color=SOLID_GREY, show_edges=True, edge_color="#52514e", line_width=0.5)
    p.view_xy(); p.camera.focal_point = (0.030, 0.030, z_mid); p.camera.zoom(9)
    path = os.path.join(out, f"{name}_mesh.png"); save(p, path); made.append(path)
    return made


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", default="figures")
    ap.add_argument("--name", default=None)
    a = ap.parse_args(argv)
    name = a.name or os.path.basename(os.path.normpath(a.case))
    made = render_all(a.case, a.out, name)
    print("\n".join(made))


if __name__ == "__main__":
    main()

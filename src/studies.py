"""T4 mesh-independence study and T5 validation, built on the sweep runner.

    .venv/bin/python -m src.studies mesh      --np 6 --jobs 1     # centre design, coarse/medium/fine at 4 m/s
    .venv/bin/python -m src.studies validate  --mesh medium --np 6 --jobs 2   # centre design at 2/4/6 m/s
    .venv/bin/python -m src.studies plate     --mesh medium --np 6 --match-mass 51.4 --h 35

Each writes a markdown report into docs/ and a CSV into results/.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from src.geometry import HeatSinkSpec, metadata, platefin_for_mass
from src.analytic import solve as analytic_solve
from src.sweep import run_one, flatten, MIRROR

CENTER = HeatSinkSpec(3.0, 2.2, 35.0, "staggered")


def _mirror(path: str) -> None:
    try:
        os.makedirs(os.path.join(MIRROR, "docs"), exist_ok=True)
        import shutil
        shutil.copy(path, os.path.join(MIRROR, "docs", os.path.basename(path)))
    except OSError:
        pass


def mesh_study(np_: int, jobs: int, iters: int, levels=("coarse", "medium", "fine"), root="work/mesh_study") -> pd.DataFrame:
    os.makedirs(root, exist_ok=True)
    caps = {"coarse": (1200, 2400), "medium": (2400, 3600), "fine": (3600, 7200)}
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        res = list(ex.map(lambda lv: run_one(CENTER, 4.0, lv, np_, iters, root, *caps[lv]), levels))
    rows = []
    for lv, r in zip(levels, res):
        rows.append({"mesh": lv, "cells_fluid": r.get("cells_fluid"), "cells_solid": r.get("cells_solid"),
                     "T_chip_max_C": (r.get("T_solid_max_K") or float("nan")) - 273.15,
                     "R_K_W": r.get("R_max_K_W"), "dP_Pa": r.get("dP_Pa"), "Q_chip_W": r.get("Q_chip_W"),
                     "iterations": r.get("iterations"), "mesh_time_min": (r.get("mesh_time_s") or 0) / 60,
                     "solve_time_min": (r.get("solver_time_s") or 0) / 60, "status": r.get("status")})
    df = pd.DataFrame(rows)
    os.makedirs("results", exist_ok=True); os.makedirs("docs", exist_ok=True)
    df.to_csv("results/mesh_study.csv", index=False)
    an = analytic_solve(metadata(CENTER), 4.0)
    lines = ["# Mesh independence study", "",
             "Centre design (d = 3 mm, p/d = 2.2, h = 35 mm, staggered) at 4 m/s, three refinement levels "
             "(background 3 mm cells; surface refinement level 2 / 3 / 4 = 0.75 / 0.375 / 0.19 mm on the pins).", "",
             "| mesh | fluid cells | solid cells | T_chip,max C | R K/W | dP Pa | Q_chip W | iterations | mesh min | solve min |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in df.iterrows():
        lines.append(f"| {r['mesh']} | {r['cells_fluid']} | {r['cells_solid']} | {r['T_chip_max_C']:.2f} | {r['R_K_W']:.4f} | "
                     f"{r['dP_Pa']:.1f} | {r['Q_chip_W']:.1f} | {r['iterations']} | {r['mesh_time_min']:.1f} | {r['solve_time_min']:.1f} |"
                     if pd.notna(r["R_K_W"]) else f"| {r['mesh']} | failed: {r['status']} | | | | | | | | |")
    ok = df.dropna(subset=["R_K_W"]).set_index("mesh")
    if {"medium", "fine"} <= set(ok.index):
        dR = abs(ok.loc["fine", "R_K_W"] / ok.loc["medium", "R_K_W"] - 1) * 100
        dP = abs(ok.loc["fine", "dP_Pa"] / ok.loc["medium", "dP_Pa"] - 1) * 100
        verdict = "PASS (< 3 %)" if max(dR, dP) < 3 else "FAIL (> 3 %)"
        lines += ["", f"Medium-to-fine change: R {dR:.1f} %, dP {dP:.1f} % -> {verdict}.",
                  "" if max(dR, dP) < 3 else "The sweep uses the medium mesh anyway (documented limitation); see DECISIONS.md."]
    if {"coarse", "medium"} <= set(ok.index):
        dR = abs(ok.loc["medium", "R_K_W"] / ok.loc["coarse", "R_K_W"] - 1) * 100
        dP = abs(ok.loc["medium", "dP_Pa"] / ok.loc["coarse", "dP_Pa"] - 1) * 100
        lines += [f"Coarse-to-medium change: R {dR:.1f} %, dP {dP:.1f} %."]
    lines += ["", f"Hand calculation for reference: R = {an['R_total_K_W']:.3f} K/W, dP = {an['dP_Pa']:.0f} Pa."]
    with open("docs/mesh_study.md", "w") as f:
        f.write("\n".join(lines) + "\n")
    _mirror("docs/mesh_study.md")
    print("\n".join(lines))
    return df


def validation(mesh: str, np_: int, jobs: int, iters: int, root="work/validation") -> pd.DataFrame:
    os.makedirs(root, exist_ok=True)
    Vs = [2.0, 4.0, 6.0]
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        res = list(ex.map(lambda V: run_one(CENTER, V, mesh, np_, iters, root, 2400, 3600), Vs))
    meta = metadata(CENTER)
    rows = []
    for V, r in zip(Vs, res):
        an = analytic_solve(meta, V)
        rows.append({"V": V, "R_cfd": r.get("R_max_K_W"), "R_hand": an["R_total_K_W"], "R_hand_zukauskas": an["R_total_zukauskas_K_W"],
                     "dP_cfd": r.get("dP_Pa"), "dP_hand": an["dP_Pa"], "T_out_cfd_C": (r.get("T_out_K") or float("nan")) - 273.15,
                     "T_out_hand_C": an["T_out"], "Q_chip_W": r.get("Q_chip_W"), "Q_balance_W": r.get("Q_energy_balance_W"),
                     "status": r.get("status")})
    df = pd.DataFrame(rows)
    df["R_ratio"] = df["R_cfd"] / df["R_hand"]
    df["dP_ratio"] = df["dP_cfd"] / df["dP_hand"]
    os.makedirs("results", exist_ok=True); os.makedirs("docs", exist_ok=True)
    df.to_csv("results/validation.csv", index=False)
    lines = ["# Validation against hand calculations", "",
             f"Centre design, {mesh} mesh. Hand calculation: ESDU 73031 (Nu), Gaddis-Gnielinski (dP), pin-fin efficiency, "
             "NTU treatment of the array, Lee et al. spreading resistance (see src/analytic.py).", "",
             "| V m/s | R CFD | R hand | ratio | dP CFD | dP hand | ratio | T_out CFD | T_out hand | Q chip W | Q air W |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in df.iterrows():
        if pd.notna(r["R_cfd"]):
            lines.append(f"| {r['V']:.0f} | {r['R_cfd']:.3f} | {r['R_hand']:.3f} | {r['R_ratio']:.2f} | {r['dP_cfd']:.0f} | "
                         f"{r['dP_hand']:.0f} | {r['dP_ratio']:.2f} | {r['T_out_cfd_C']:.1f} | {r['T_out_hand_C']:.1f} | "
                         f"{r['Q_chip_W']:.1f} | {r['Q_balance_W']:.1f} |")
        else:
            lines.append(f"| {r['V']:.0f} | failed: {r['status']} | | | | | | | | | |")
    ok = df.dropna(subset=["R_cfd"])
    if len(ok):
        worst_R = (ok["R_ratio"] - 1).abs().max() * 100
        worst_P = (ok["dP_ratio"] - 1).abs().max() * 100
        lines += ["", f"Largest deviation: R {worst_R:.0f} %, dP {worst_P:.0f} % -> "
                  + ("PASS (within 30 %)." if max(worst_R, worst_P) <= 30 else "outside the 30 % target; see discussion below."),
                  "", "## Discussion", "",
                  "The correlations describe long tube banks with uniform approach flow. Differences to expect: the 4 mm step onto the "
                  "base plate and the shroud contact at the pin tips are not in the hand calculation; the array has only 5-16 rows "
                  "(row-correction factors carry their own uncertainty); the CFD uses wall functions on a 0.4 mm mesh with no prism "
                  "layers; and the correlation uncertainty itself is quoted at about 15-25 %."]
    with open("docs/validation.md", "w") as f:
        f.write("\n".join(lines) + "\n")
    _mirror("docs/validation.md")
    print("\n".join(lines))
    return df


def plate_comparison(mesh: str, np_: int, iters: int, match_mass: float, h: float, t: float, root="work/plate") -> dict:
    spec = platefin_for_mass(match_mass, h, t)
    r = run_one(spec, 4.0, mesh, np_, iters, root, 2400, 3600)
    os.makedirs("results", exist_ok=True)
    with open("results/plate_comparison.json", "w") as f:
        json.dump({"spec": spec.__dict__, "result": {k: r.get(k) for k in ("R_max_K_W", "dP_Pa", "T_solid_max_K", "status")}}, f, indent=2)
    print(json.dumps(r.get("R_max_K_W")), r.get("dP_Pa"))
    return r


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["mesh", "validate", "plate"])
    ap.add_argument("--mesh", default="medium")
    ap.add_argument("--np", type=int, default=6)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--iters", type=int, default=1500)
    ap.add_argument("--levels", nargs="*", default=["coarse", "medium", "fine"])
    ap.add_argument("--match-mass", type=float, default=51.4)
    ap.add_argument("--h", type=float, default=35.0)
    ap.add_argument("--t", type=float, default=1.5)
    a = ap.parse_args(argv)
    if a.what == "mesh":
        mesh_study(a.np, a.jobs, a.iters, tuple(a.levels))
    elif a.what == "validate":
        validation(a.mesh, a.np, a.jobs, a.iters)
    else:
        plate_comparison(a.mesh, a.np, a.iters, a.match_mass, a.h, a.t)


if __name__ == "__main__":
    main()

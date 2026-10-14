"""Run the conjugate heat-transfer simulation on any heat sink CAD file (STEP or STL).

    python -m src.run --cad my_sink.step --chip 30x30 --power 100 --V 4 --out results/cad/my_sink
    python -m src.run --cad-dir sinks/   --chip 30x30 --power 100 --V 4 --out results/cad/batch
    python -m src.run --inspect my_sink.step           # measurements and a top-view PNG, nothing is run
    python -m src.run --cad my_sink.step --dry-run     # import, measure, write the case, no mesher or solver

Exit codes: 0 ok, 2 input refused, 3 meshing failed, 4 solver failed or timed out. See docs/cad_input.md.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import shutil
import sys
import time

from src import cad_import as ci
from src import make_case as mc
from src import runner

SUFFIXES = (".step", ".stp", ".stl")
EXIT_OK, EXIT_REFUSED, EXIT_MESH, EXIT_SOLVER = 0, 2, 3, 4

CSV_COLUMNS = ["name", "file", "V", "mesh", "status", "n_fins", "fin_mass_g", "R_max_K_W", "T_solid_max_K",
               "dP_Pa", "Q_chip_W", "interface_balance_err_pct", "cells_fluid", "cells_solid", "iterations",
               "wall_s", "warnings"]


def parse_chip(text: str) -> tuple[float, float]:
    try:
        parts = [float(p) for p in text.lower().replace("*", "x").split("x")]
    except ValueError:
        raise ci.InputRefused(f"cannot read --chip {text!r}; use 30x30 or 30 (mm)")
    if len(parts) == 1:
        parts = parts * 2
    if len(parts) != 2 or min(parts) <= 0:
        raise ci.InputRefused(f"cannot read --chip {text!r}; use 30x30 or 30 (mm)")
    return parts[0], parts[1]


def parse_offset(text: str) -> tuple[float, float]:
    try:
        a, b = [float(p) for p in text.split(",")]
    except ValueError:
        raise ci.InputRefused(f"cannot read --chip-offset {text!r}; use dx,dy in mm, e.g. 5,-3")
    return a, b


def find_inputs(a) -> list[str]:
    if a.cad:
        if not os.path.isfile(a.cad):
            raise ci.InputRefused(f"file not found: {a.cad}")
        return [a.cad]
    if not os.path.isdir(a.cad_dir):
        raise ci.InputRefused(f"folder not found: {a.cad_dir}")
    files = sorted(f for f in glob.glob(os.path.join(a.cad_dir, "*")) if f.lower().endswith(SUFFIXES))
    if not files:
        raise ci.InputRefused(f"no .step, .stp or .stl files in {a.cad_dir}")
    stems = [os.path.splitext(os.path.basename(f))[0] for f in files]
    dup = sorted({s for s in stems if stems.count(s) > 1})
    if dup:
        raise ci.InputRefused(f"two files share the name {dup[0]!r}; rename one so the case folders stay apart")
    return files


def row_from_result(res: dict, file: str) -> dict:
    meta = res.get("meta", {})
    warn = (meta.get("model") or {}).get("warnings", [])
    row = {c: res.get(c) for c in CSV_COLUMNS}
    row.update({"file": os.path.basename(file), "V": meta.get("V"), "mesh": meta.get("mesh"),
                "n_fins": meta.get("n_pins"), "fin_mass_g": meta.get("fin_mass_g"), "warnings": "; ".join(warn)})
    return row


def pareto(rows: list[dict]) -> list[dict]:
    """Non-dominated rows (low R, low dP) within each velocity."""
    out = []
    ok = [r for r in rows if r["status"] == "ok" and r["R_max_K_W"] is not None and r["dP_Pa"] is not None]
    for v in sorted({r["V"] for r in ok}):
        best = float("inf")
        for r in sorted((r for r in ok if r["V"] == v), key=lambda r: (r["dP_Pa"], r["R_max_K_W"])):
            if r["R_max_K_W"] < best:
                out.append(r)
                best = r["R_max_K_W"]
    return out


def write_summary(out: str, rows: list[dict], title: str) -> None:
    with open(os.path.join(out, "sweep.csv"), "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        wr.writeheader()
        wr.writerows(rows)
    front = pareto(rows)
    with open(os.path.join(out, "pareto.csv"), "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        wr.writeheader()
        wr.writerows(front)
    ok = [r for r in rows if r["status"] == "ok" and r["R_max_K_W"] is not None]
    if ok:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7.0, 4.6))
        for r in ok:
            ax.scatter(r["dP_Pa"], r["R_max_K_W"], s=46, color="#1f6e8c", zorder=3)
            ax.annotate(os.path.splitext(r["file"])[0], (r["dP_Pa"], r["R_max_K_W"]), xytext=(6, 5),
                        textcoords="offset points", fontsize=8, color="#444")
        if len(front) > 1:
            ax.plot([r["dP_Pa"] for r in front], [r["R_max_K_W"] for r in front], color="#1b1f23", lw=1.2,
                    label="Pareto front", zorder=2)
            ax.legend(fontsize=8, frameon=False)
        ax.set_xlabel("Pressure drop across the heat sink, Pa")
        ax.set_ylabel("Thermal resistance, hottest solid point to inlet, K/W")
        ax.set_title(title, loc="left", fontsize=11)
        ax.grid(color="#e4e4e0", lw=0.6)
        fig.tight_layout()
        fig.savefig(os.path.join(out, "pareto.png"), dpi=150)
        plt.close(fig)
    lines = [f"# {title}", "",
             "No hand calculation exists for these shapes; values are CFD only, on the mesh level named in the table. "
             "R = (hottest solid temperature - inlet temperature) / chip power. The study's own limitations "
             "(no mesh-independence proof, residual criteria not met) apply; see docs/cad_input.md.", "",
             "| file | V m/s | mesh | status | fins | fin mass g | R K/W | dP Pa | Q chip W |", "|---|---|---|---|---|---|---|---|---|"]
    fmt = lambda v, f: "-" if v is None else format(v, f)
    for r in rows:
        lines.append(f"| {r['file']} | {fmt(r['V'], 'g')} | {r['mesh']} | {r['status']} | {fmt(r['n_fins'], 'd')} | "
                     f"{fmt(r['fin_mass_g'], '.1f')} | {fmt(r['R_max_K_W'], '.3f')} | {fmt(r['dP_Pa'], '.0f')} | "
                     f"{fmt(r['Q_chip_W'], '.1f')} |")
    warns = [(r["file"], r["warnings"]) for r in rows if r["warnings"]]
    if warns:
        lines += ["", "## Warnings from the importer", ""] + [f"- {f}: {w}" for f, w in dict(warns).items()]
    with open(os.path.join(out, "results.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--cad", help="one STEP or STL file")
    g.add_argument("--cad-dir", help="a folder of STEP/STL files, run one after the other")
    g.add_argument("--inspect", metavar="FILE", help="print the measurements and write <stem>_inspect.png, run nothing")
    ap.add_argument("--chip", default="30x30", help="chip size x by y in mm (default 30x30)")
    ap.add_argument("--chip-offset", default="0,0", help="chip centre offset from the base centre, dx,dy in mm")
    ap.add_argument("--power", type=float, default=100.0, help="chip power, W")
    ap.add_argument("--material", choices=list(mc.MATERIALS), default="aluminium")
    ap.add_argument("--V", type=float, action="append", help="inlet speed m/s, may be repeated (default 4)")
    ap.add_argument("--mesh", choices=list(mc.MESH_LEVELS), default="coarse")
    ap.add_argument("--np", type=int, default=8, help="MPI processes")
    ap.add_argument("--iters", type=int, default=600)
    ap.add_argument("--layers", type=int, default=4, help="prism layers on the sink surface")
    ap.add_argument("--orient", default="auto", help="auto, none, or rotations such as 'x90 z-90'")
    ap.add_argument("--units", default="auto", choices=["auto", "mm", "m", "in"])
    ap.add_argument("--surf-level", type=int, default=None, help="override the surface refinement level")
    ap.add_argument("--base-cell", type=float, default=3.0, help="background cell size, mm")
    ap.add_argument("--out", default=None, help="output folder (default results/cad/<name>)")
    ap.add_argument("--dry-run", action="store_true", help="import, measure and write the case; no mesher, no solver")
    ap.add_argument("--mesh-timeout", type=int, default=3600)
    ap.add_argument("--solve-timeout", type=int, default=2700)
    ap.add_argument("--flavour", choices=["org", "esi"], default="org", help="esi = mesh-only cloud testing")
    ap.add_argument("--title", default="Heat sink CFD results")
    return ap


def inspect(a) -> int:
    stem = os.path.splitext(os.path.basename(a.inspect))[0]
    out = a.out or "."
    os.makedirs(out, exist_ok=True)
    m = ci.load(a.inspect, a.units, a.orient, out_dir=os.path.join(out, f"{stem}_import"))
    chip = None
    try:
        chip = ci.chip_rect(m, parse_chip(a.chip), parse_offset(a.chip_offset))
    except ci.InputRefused as e:
        print(f"note: {e}")
    print(ci.describe(m))
    png = ci.inspect_figure(m, os.path.join(out, f"{stem}_inspect.png"), chip)
    print(f"figure: {png}")
    return EXIT_OK


def run_file(path: str, a, out: str, velocities: list[float]) -> tuple[list[dict], int]:
    stem = os.path.splitext(os.path.basename(path))[0]
    model = ci.load(path, a.units, a.orient, out_dir=os.path.join(out, f"{stem}_import"))
    for w in model.warnings:
        print(f"warning ({stem}): {w}")
    dom = mc.domain_from_model(model, parse_chip(a.chip), parse_offset(a.chip_offset), a.power, a.material,
                               a.base_cell * 1e-3)
    rows, code = [], EXIT_OK
    for V in velocities:
        name = f"{stem}_V{V:g}_{a.mesh}"
        case = os.path.join(out, name)
        if not a.dry_run and runner.already_done(case):
            runner.log(f"skip {name} (done)")
            with open(os.path.join(case, "results.json")) as f:
                rows.append(row_from_result(json.load(f), path))
            continue
        t0 = time.time()
        shutil.rmtree(case, ignore_errors=True)
        mc.write_case_from_model(model, dom, V, a.mesh, case, a.np, a.iters, a.flavour, a.layers, a.surf_level)
        if a.dry_run:
            print(f"wrote {case}")
            continue
        status, reason, stage = runner.mesh_and_solve(case, name, a.np, a.mesh_timeout, a.solve_timeout)
        res = runner.finish(case, name, status, reason, t0, {"model": model.to_dict()})
        rows.append(row_from_result(res, path))
        if status != "ok":
            code = max(code, EXIT_MESH if stage == "mesh" else EXIT_SOLVER)
            print(f"{name}: {status} ({reason}); see {case}/log.Allmesh and log.solve")
    return rows, code


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    try:
        if a.inspect:
            return inspect(a)
        files = find_inputs(a)
        velocities = a.V or [4.0]
        out = a.out or os.path.join("results", "cad", os.path.splitext(os.path.basename(a.cad or a.cad_dir.rstrip("/\\")))[0])
        os.makedirs(out, exist_ok=True)
        rows, code = [], EXIT_OK
        for f in files:
            try:
                r, c = run_file(f, a, out, velocities)
            except ci.InputRefused as e:
                if len(files) == 1:
                    raise
                print(f"refused {os.path.basename(f)}: {e}")
                code = max(code, EXIT_REFUSED)
                continue
            rows += r
            code = max(code, c)
        if rows and not a.dry_run:
            write_summary(out, rows, a.title)
            print(f"summary: {out}/results.md")
        return code
    except ci.InputRefused as e:
        print(f"refused: {e}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())

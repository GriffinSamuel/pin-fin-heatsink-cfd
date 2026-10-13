"""Design sweep runner (T6): generates, meshes, solves and parses many cases on the laptop.

Runs N cases concurrently (default 2), each with its own MPI processes (default 6), with
wall-clock caps on meshing and solving. Resumable: a case whose results.json already holds a
temperature result is skipped. After every case, results/sweep.csv is rewritten from all
results.json files found, and the summary is mirrored to the Windows results folder.

Usage (inside WSL, from the repo root, OpenFOAM 14 sourced):
    .venv/bin/python -m src.sweep --mesh medium --V 4 --np 6 --jobs 2 [--only d3_pd2.2_h35_staggered ...]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import itertools
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from src.geometry import HeatSinkSpec
from src.make_case import write_case
from src.results import parse_case

D_LIST = [2.0, 3.0, 4.0]
PD_LIST = [1.8, 2.2, 2.8]
H_LIST = [20.0, 35.0]
LAYOUTS = ["inline", "staggered"]
MIRROR = "/mnt/c/Users/Griff/Projects/heatsink-cfd/results"

COLUMNS = ["name", "d", "pd", "h", "layout", "V", "mesh", "status", "n_pins", "n_rows", "fin_mass_g",
           "T_solid_max_K", "R_max_K_W", "R_chip_avg_K_W", "dP_Pa", "Q_chip_W", "Q_energy_balance_W",
           "m_dot_in_kg_s", "T_out_K", "iterations", "solver_time_s", "mesh_time_s", "cells_fluid",
           "cells_solid", "mesh_ok_fluid", "mesh_ok_solid", "analytic_R_K_W", "analytic_dP_Pa",
           "res_U", "res_h", "res_p", "wall_s", "fail_reason"]


def design_matrix() -> list[HeatSinkSpec]:
    return [HeatSinkSpec(d, pd, h, lay) for d, pd, h, lay in itertools.product(D_LIST, PD_LIST, H_LIST, LAYOUTS)]


def log(msg: str) -> None:
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def run(cmd: list[str], cwd: str, logfile: str, timeout: int) -> int:
    with open(logfile, "w") as f:
        try:
            p = subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, timeout=timeout)
            return p.returncode
        except subprocess.TimeoutExpired:
            f.write(f"\nTIMEOUT after {timeout} s\n")
            return 124


def already_done(case_dir: str) -> bool:
    p = os.path.join(case_dir, "results.json")
    if not os.path.exists(p):
        return False
    with open(p) as f:
        r = json.load(f)
    return r.get("T_solid_max_K") is not None and r.get("status", "ok") == "ok"


def run_one(spec: HeatSinkSpec, V: float, mesh: str, n_proc: int, n_iter: int, root: str,
            mesh_timeout: int, solve_timeout: int) -> dict:
    name = f"{spec.name}_V{V:g}_{mesh}"
    case = os.path.join(root, name)
    if already_done(case):
        log(f"skip {name} (done)")
        with open(os.path.join(case, "results.json")) as f:
            return json.load(f)
    t0 = time.time()
    shutil.rmtree(case, ignore_errors=True)
    write_case(spec, V, mesh, case, n_proc, n_iter)
    env = os.environ.copy()
    status, reason = "ok", ""
    log(f"mesh  {name}")
    rc = run(["bash", "./Allmesh"], case, os.path.join(case, "log.Allmesh"), mesh_timeout)
    ok_fluid = os.path.exists(os.path.join(case, "constant", "fluid", "polyMesh", "faces"))
    if rc != 0 or not ok_fluid:
        status, reason = "failed", f"mesh rc={rc}"
    else:
        log(f"solve {name}")
        rc = run(["bash", "-c", f"decomposePar -allRegions > log.decomposePar 2>&1 && "
                                 f"mpirun -np {n_proc} foamMultiRun -parallel > log.foamMultiRun 2>&1; "
                                 f"rc=$?; reconstructPar -allRegions -latestTime > log.reconstructPar 2>&1; exit $rc"],
                 case, os.path.join(case, "log.solve"), solve_timeout)
        if rc == 124:
            status, reason = "timeout", "solver exceeded cap"
        elif rc != 0:
            status, reason = "failed", f"solver rc={rc}"
        for p in glob.glob(os.path.join(case, "processor*")):
            shutil.rmtree(p, ignore_errors=True)
    res = parse_case(case)
    res.update({"status": status, "fail_reason": reason, "wall_s": time.time() - t0, "name": name})
    with open(os.path.join(case, "results.json"), "w") as f:
        json.dump(res, f, indent=2)
    log(f"done  {name}: {status} T_max={res.get('T_solid_max_K')} dP={res.get('dP_Pa')} in {res['wall_s']/60:.1f} min")
    return res


def flatten(r: dict) -> dict:
    m = r.get("meta", {})
    s = m.get("spec", {})
    an = m.get("analytic", {})
    rf = r.get("residuals_fluid", {}) or {}
    row = {
        "name": r.get("name"), "d": s.get("d"), "pd": s.get("pd"), "h": s.get("h"), "layout": s.get("layout"),
        "V": m.get("V"), "mesh": m.get("mesh"), "status": r.get("status"), "n_pins": m.get("n_pins"),
        "n_rows": m.get("n_rows"), "fin_mass_g": m.get("fin_mass_g"),
        "analytic_R_K_W": an.get("R_total_K_W"), "analytic_dP_Pa": an.get("dP_Pa"),
        "res_U": rf.get("Ux", rf.get("U")), "res_h": rf.get("h"), "res_p": rf.get("p"),
    }
    for k in COLUMNS:
        if k not in row:
            row[k] = r.get(k)
    return row


def write_csv(root: str, out_csv: str) -> int:
    rows = []
    for p in sorted(glob.glob(os.path.join(root, "*", "results.json"))):
        with open(p) as f:
            rows.append(flatten(json.load(f)))
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=COLUMNS)
        wr.writeheader()
        wr.writerows(rows)
    try:
        os.makedirs(MIRROR, exist_ok=True)
        shutil.copy(out_csv, os.path.join(MIRROR, os.path.basename(out_csv)))
    except OSError:
        pass
    return len(rows)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", default="medium")
    ap.add_argument("--V", type=float, nargs="+", default=[4.0])
    ap.add_argument("--np", type=int, default=6)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--iters", type=int, default=1500)
    ap.add_argument("--root", default="work/sweep")
    ap.add_argument("--csv", default="results/sweep.csv")
    ap.add_argument("--only", nargs="*", default=None, help="design names to run")
    ap.add_argument("--mesh-timeout", type=int, default=1800)
    ap.add_argument("--solve-timeout", type=int, default=2700)
    a = ap.parse_args(argv)
    specs = design_matrix()
    if a.only:
        specs = [s for s in specs if s.name in a.only]
    jobs = [(s, V) for V in a.V for s in specs]
    log(f"{len(jobs)} cases, mesh={a.mesh}, np={a.np}, {a.jobs} at a time")
    os.makedirs(a.root, exist_ok=True)

    def work(sv):
        s, V = sv
        try:
            r = run_one(s, V, a.mesh, a.np, a.iters, a.root, a.mesh_timeout, a.solve_timeout)
        except Exception as e:  # keep the sweep alive
            log(f"ERROR {s.name} V={V}: {e!r}")
            r = {"name": f"{s.name}_V{V:g}_{a.mesh}", "status": "error", "fail_reason": repr(e)}
            case = os.path.join(a.root, r["name"])
            os.makedirs(case, exist_ok=True)
            with open(os.path.join(case, "results.json"), "w") as f:
                json.dump(r, f)
        n = write_csv(a.root, a.csv)
        log(f"csv updated ({n} rows)")
        return r

    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        results = list(ex.map(work, jobs))
    ok = sum(1 for r in results if r.get("status") == "ok")
    log(f"sweep finished: {ok}/{len(results)} ok")
    write_csv(a.root, a.csv)


if __name__ == "__main__":
    main()

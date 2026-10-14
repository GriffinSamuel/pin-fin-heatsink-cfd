"""Shared case runner: mesh, solve, parse. Used by sweep.py, studies.py (through sweep.run_one) and run.py.

The mesh and solve commands, the caps and the resume rule (a case whose results.json holds a temperature and
status ok is skipped) are exactly those of the T6 sweep; they were moved here from sweep.py unchanged."""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import shutil
import subprocess
import time

from src.results import parse_case


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


def mesh_and_solve(case: str, name: str, n_proc: int, mesh_timeout: int, solve_timeout: int) -> tuple[str, str, str]:
    """Run Allmesh and the solver in `case`. Returns (status, reason, stage) with stage in {"mesh", "solve"}
    marking where a failure happened ("" when ok)."""
    status, reason, stage = "ok", "", ""
    log(f"mesh  {name}")
    rc = run(["bash", "./Allmesh"], case, os.path.join(case, "log.Allmesh"), mesh_timeout)
    ok_fluid = os.path.exists(os.path.join(case, "constant", "fluid", "polyMesh", "faces"))
    if rc != 0 or not ok_fluid:
        return "failed", f"mesh rc={rc}", "mesh"
    log(f"solve {name}")
    rc = run(["bash", "-c", f"decomposePar -allRegions > log.decomposePar 2>&1 && "
                            f"mpirun -np {n_proc} foamMultiRun -parallel > log.foamMultiRun 2>&1; "
                            f"rc=$?; reconstructPar -allRegions -latestTime > log.reconstructPar 2>&1; exit $rc"],
             case, os.path.join(case, "log.solve"), solve_timeout)
    if rc == 124:
        status, reason, stage = "timeout", "solver exceeded cap", "solve"
    elif rc != 0:
        status, reason, stage = "failed", f"solver rc={rc}", "solve"
    for p in glob.glob(os.path.join(case, "processor*")):
        shutil.rmtree(p, ignore_errors=True)
    return status, reason, stage


def finish(case: str, name: str, status: str, reason: str, t0: float, extra: dict | None = None) -> dict:
    """Parse the case, add status and timing, write results.json."""
    res = parse_case(case)
    res.update({"status": status, "fail_reason": reason, "wall_s": time.time() - t0, "name": name})
    if extra:
        res.update(extra)
    with open(os.path.join(case, "results.json"), "w") as f:
        json.dump(res, f, indent=2)
    log(f"done  {name}: {status} T_max={res.get('T_solid_max_K')} dP={res.get('dP_Pa')} in {res['wall_s']/60:.1f} min")
    return res

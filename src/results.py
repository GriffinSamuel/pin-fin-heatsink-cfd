"""Parse an OpenFOAM 14 case directory (after foamMultiRun) into results.json.

Reads the function-object output under postProcessing/ (last time written), the
solver log for timing, and case.json for the design parameters and analytic prediction.
Robust to the exact directory naming of #includeFunc objects: every *.dat file is scanned
and classified by the keywords in its path.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

T_IN = 298.15
Q_NOMINAL = 100.0


def _last_data_line(path: str) -> list[str] | None:
    last = None
    with open(path) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            last = line.split()
    return last


def _rows(path: str) -> list[list[str]]:
    out = []
    with open(path) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            out.append(line.split())
    return out


def _find(case: str, *keys: str) -> list[str]:
    """All .dat files whose path contains every key (keys are matched case-sensitively)."""
    files = glob.glob(os.path.join(case, "postProcessing", "**", "*.dat"), recursive=True)
    return sorted(f for f in files if all(k in f for k in keys))


def parse_case(case: str) -> dict:
    res: dict = {"case": os.path.abspath(case)}
    meta_path = os.path.join(case, "case.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            res["meta"] = json.load(f)

    def scalar(keys, col=1, which="last"):
        files = _find(case, *keys)
        if not files:
            return None
        rows = _rows(files[-1])
        if not rows:
            return None
        return float(rows[-1][col])

    # temperatures
    res["T_solid_max_K"] = scalar(["cellMax", "solid", "T"])
    res["T_solid_min_K"] = scalar(["cellMin", "solid", "T"])
    res["T_fluid_max_K"] = scalar(["cellMax", "fluid", "T"])
    res["T_chip_avg_K"] = scalar(["patchAverage", "solid", "chip", "T"])
    res["T_out_K"] = scalar(["patchAverage", "fluid", "outlet", "T"])
    res["T_in_K"] = scalar(["patchAverage", "fluid", "inlet", "T"])
    # pressures and mass flow
    p_in = scalar(["patchAverage", "fluid", "inlet", "p"])
    p_out = scalar(["patchAverage", "fluid", "outlet", "p"])
    res["p_in_Pa"], res["p_out_Pa"] = p_in, p_out
    res["dP_Pa"] = (p_in - p_out) if (p_in is not None and p_out is not None) else None
    m_in = scalar(["patchFlowRate", "fluid", "inlet", "phi"])
    m_out = scalar(["patchFlowRate", "fluid", "outlet", "phi"])
    res["m_dot_in_kg_s"] = -m_in if m_in is not None else None    # phi is outward-positive
    res["m_dot_out_kg_s"] = m_out

    # heat flux integrals: wallHeatFlux writes one row per patch per time
    for region in ("solid", "fluid"):
        files = _find(case, "wallHeatFlux", region)
        if not files:
            continue
        rows = _rows(files[-1])
        if not rows:
            continue
        last_t = rows[-1][0]
        for r in rows:
            if r[0] == last_t and len(r) >= 5:
                try:
                    res[f"Q_{region}_{r[1]}_W"] = float(r[4])
                except ValueError:
                    pass

    q_chip = res.get("Q_solid_chip_W")
    res["Q_chip_W"] = q_chip
    q_used = abs(q_chip) if q_chip else Q_NOMINAL
    if res["T_solid_max_K"] is not None:
        res["R_max_K_W"] = (res["T_solid_max_K"] - T_IN) / q_used
    if res["T_chip_avg_K"] is not None:
        res["R_chip_avg_K_W"] = (res["T_chip_avg_K"] - T_IN) / q_used
    if res["T_out_K"] is not None and res["m_dot_in_kg_s"]:
        res["Q_energy_balance_W"] = res["m_dot_in_kg_s"] * 1006.0 * (res["T_out_K"] - T_IN)

    # residuals (initial residual of the last iteration)
    for region in ("fluid", "solid"):
        files = _find(case, "residuals", region)
        if files:
            with open(files[-1]) as f:
                header = [l for l in f if l.startswith("#")]
            cols = header[-1].lstrip("#").split() if header else []
            last = _last_data_line(files[-1])
            if last and cols and len(cols) == len(last):
                res[f"residuals_{region}"] = {c: float(v) for c, v in zip(cols[1:], last[1:])}
            elif last:
                res[f"residuals_{region}"] = {f"c{i}": float(v) for i, v in enumerate(last[1:])}

    # solver log: iterations and execution time
    log = os.path.join(case, "log.foamMultiRun")
    if os.path.exists(log):
        n_iter, exec_t, converged = 0, None, False
        with open(log, errors="replace") as f:
            for line in f:
                if line.startswith("Time = "):
                    n_iter = int(float(line.split("=")[1]))
                elif line.startswith("ExecutionTime"):
                    exec_t = float(line.split()[2])
                elif "converged" in line.lower() and "residual" in line.lower():
                    converged = True
        res["iterations"] = n_iter
        res["solver_time_s"] = exec_t
        res["converged_by_residualControl"] = converged
    for name in ("log.snappyHexMesh",):
        p = os.path.join(case, name)
        if os.path.exists(p):
            with open(p, errors="replace") as f:
                txt = f.read()
            m = re.findall(r"Snapped mesh : cells:(\d+)", txt)
            if m:
                res["mesh_cells_total"] = int(m[-1])
            m = re.findall(r"Finished meshing in = ([0-9.]+) s", txt)
            if m:
                res["mesh_time_s"] = float(m[-1])
    for region in ("fluid", "solid"):
        p = os.path.join(case, f"log.checkMesh.{region}")
        if os.path.exists(p):
            with open(p, errors="replace") as f:
                txt = f.read()
            m = re.search(r"cells:\s+(\d+)", txt)
            if m:
                res[f"cells_{region}"] = int(m.group(1))
            res[f"mesh_ok_{region}"] = "Mesh OK" in txt
    return res


def main(argv=None):
    case = (argv or sys.argv[1:])[0]
    res = parse_case(case)
    with open(os.path.join(case, "results.json"), "w") as f:
        json.dump(res, f, indent=2)
    keys = ["T_solid_max_K", "R_max_K_W", "dP_Pa", "Q_chip_W", "Q_energy_balance_W", "m_dot_in_kg_s",
            "iterations", "solver_time_s", "mesh_cells_total"]
    print(json.dumps({k: res.get(k) for k in keys}, indent=1))


if __name__ == "__main__":
    main()

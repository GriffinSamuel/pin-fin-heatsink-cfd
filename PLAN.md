# Pin-Fin Heat Sink Optimization: CAD + CFD + Surrogate Model

Portfolio project for NVIDIA Ignite (hardware track). Owner: Griffin. Target: Oct 18, 2026.
Executed by a Claude Code loop (see LOOP_PROMPT.md and loop.sh).

## Goal
Design an air-cooled pin-fin heat sink for a 100 W, 30 x 30 mm chip, sweep the fin geometry with
real CFD (OpenFOAM 14, conjugate heat transfer), validate against hand calculations, find the
Pareto-optimal designs (thermal resistance vs. pressure drop), train a small GPU surrogate model
on the results, and publish a clean GitHub repo with a report and figures.

## Fixed problem definition (do not change)
- Chip: 30 x 30 mm, 100 W uniform heat flux on the underside of the base plate.
- Heat sink base: 60 x 60 mm, aluminum (k = 200 W/m-K), base thickness fixed at 4 mm.
- Air: 25 C inlet, duct flow over the fins, inlet velocities 2, 4, 6 m/s.
- Domain: duct 60 mm wide, height = base thickness + fin height (shroud touches the pin tips,
  no bypass), 60 mm upstream, 120 mm downstream. Base plate sits on the floor as a 4 mm step.
- Turbulence: k-omega SST, steady state, OpenFOAM 14 multi-region (fluid + solid) solver.
- Outputs per case: base max temperature, thermal resistance R = (T_base_max - 25)/100 [K/W],
  pressure drop dP [Pa], fin mass [g], final residuals, wall-clock time.

## Design variables (the sweep)
- pin diameter d: 2, 3, 4 mm
- pitch/diameter ratio p/d: 1.8, 2.2, 2.8
- fin height h: 20, 35 mm
- layout: inline, staggered
Full factorial = 36 geometries. Run all 36 at 4 m/s first; run 2 and 6 m/s only for the
10 best designs if time allows.

## Environment (verified on this laptop on Oct 11)
- WSL2 Ubuntu 26.04, OpenFOAM 14 at /opt/openfoam14 (source /opt/openfoam14/etc/bashrc).
- 14 cores and 25 GB RAM visible to Linux; RTX 5070 8 GB visible via nvidia-smi.
- Measured on a 3.2M-cell case: meshing ~4 min, solving ~2 s/iteration on 8 processes;
  12 processes was slower than 8. Default: 6 processes per case, 2 cases at a time.
- Simulations run in ~/heatsink-cfd/work (Linux disk). Only small results go into the repo.

## Tasks with acceptance tests (the loop works through PROGRESS.md in order)

T0 Environment and repo
  - git init; .gitignore (work/, processor*, log.*, *.vtk, *.vtp); Python venv with cadquery,
    numpy, pandas, matplotlib, scipy, scikit-learn, trimesh, pyvista, pytest; torch with CUDA.
  - scripts/env_check.sh prints OpenFOAM version, nproc, free -g, nvidia-smi, python imports.
  - PASS: env_check.sh exits 0; output saved to docs/env.txt.

T1 Parametric geometry (src/geometry.py)
  - make_heatsink(d, pd, h, layout) -> CadQuery solid; exports STEP and STL for the solid,
    plus STLs for the duct and the chip patch (named surfaces for snappyHexMesh).
  - PASS: tests/test_geometry.py: 3 variants build; STL watertight (trimesh); fin count and
    solid volume match analytic values within 1%.

T2 Hand-calculation baseline (src/analytic.py)
  - Zukauskas tube-bank correlations (Nusselt number and pressure drop) for the pin array,
    fin efficiency, spreading resistance for the 30 mm chip on the 60 mm base.
  - PASS: tests/test_analytic.py: center design gives R between 0.2 and 2 K/W and dP between
    5 and 500 Pa, and both trend correctly with velocity.

T3 CFD case generator (src/make_case.py)
  - Start from the OpenFOAM 14 tutorial under /opt/openfoam14/tutorials/multiRegion that is
    closest to a heated solid in a duct. Copy its structure; never invent dictionary syntax.
  - blockMesh background + snappyHexMesh per region (heat sink surface as a wall patch), prism
    layers on the fluid side, regions coupled with createNonConformalCouples (hotWire tutorial).
  - Fixed heat flux on the chip patch (blockMesh patch + fixedGradient T), velocity inlet,
    pressure outlet, no-slip shroud and floor, symmetry sides.
  - Function objects: chip patch max T, inlet-outlet pressure drop, residuals.
  - decomposeParDict: 6 subdomains, scotch.
  - PASS: coarse mesh (< 400k cells) of the center design: checkMesh reports "Mesh OK";
    300 iterations without crash; residuals fall 2 decades; results.json written.

T4 Mesh independence
  - Center design at 4 m/s at coarse / medium / fine (~0.4M / 1.2M / 3M cells).
  - PASS: docs/mesh_study.md with a table; medium-to-fine change in R and dP < 3%. Use the
    medium level for the sweep. If > 3%, refine once more, then accept and document it.

T5 Validation
  - Compare CFD R and dP for the center design at 3 velocities with analytic.py.
  - PASS: within 30%; docs/validation.md explains any larger gap honestly.

T6 Sweep runner (src/sweep.py)
  - Generates all 36 cases; runs 2 at a time with 6 processes each; 1500-iteration cap;
    45-minute wall-clock cap per case (via timeout; mark failed); resumable; writes
    results/sweep.csv after every case; deletes processor* dirs after reconstructPar.
  - PASS: all 36 cases finished or marked failed with a reason; at least 30 successes.

T7 Analysis (src/analysis.py)
  - Pareto front R vs dP; plots: Pareto, R vs d by layout, dP vs pitch, fin mass vs R.
  - One extra case: a plain plate-fin heat sink of equal mass, compared with the best design.
  - PASS: figures/*.png, results/pareto.csv, docs/results.md with the numbers.

T8 Surrogate model (src/surrogate.py)
  - Small MLP in PyTorch on CUDA: inputs d, p/d, h, layout, V; outputs R, dP. 5-fold CV.
    Optimize with the surrogate (scipy), then verify the predicted optimum with one real CFD case.
  - PASS: CV R^2 > 0.8 for R; verification case within 15%; docs/surrogate.md.

T9 Visuals
  - Headless pvpython renders (OpenFOAM's ParaView): solid temperature, velocity slice,
    streamlines, for the best and worst designs. Use offscreen rendering or xvfb-run.
  - PASS: at least 4 PNGs in figures/.

T10 Report and repo polish
  - README.md: problem, method, key figure, results table, how to run; docs/report.md (~2 pages);
    a "resume bullets" section with real numbers; MIT LICENSE; Makefile.
  - PASS: a fresh clone + `make quick` reproduces T1, T2 and one coarse CFD case.

T11 Independent audit
  - A fresh subagent that has not seen the work reads the repo and checks every PASS condition
    and every number in README against results/*.csv. Fix what it flags.
  - PASS: docs/audit.md with all checks green. Then append ALL_TASKS_COMPLETE to PROGRESS.md.

## Rules for the loop
- Never ask the user anything. When something is ambiguous, pick the simplest option that keeps
  the physics honest, write it to DECISIONS.md, and continue.
- If a task fails 3 distinct attempts, write why to BLOCKERS.md, mark it BLOCKED in PROGRESS.md,
  and move on to the next task that does not depend on it.
- Every solver run goes through `timeout`. No single solver run may exceed 45 minutes.
- Never run more than 12 solver processes at once.
- Commit after every completed task: "T<n>: <what passed>".
- Do not edit PLAN.md. PROGRESS.md is the single source of truth for status.

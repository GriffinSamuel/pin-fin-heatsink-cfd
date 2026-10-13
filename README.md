# Pin-fin heat sink optimisation with CAD + CFD + a GPU surrogate

Design study of an air-cooled pin-fin heat sink for a 100 W, 30 x 30 mm chip: parametric CAD,
hand calculations, conjugate heat transfer CFD in OpenFOAM 14 (36-design sweep), mesh and
validation studies, Pareto analysis, and a small PyTorch surrogate model trained on the sweep
and used to search the design space.

> Status: in progress. Sections marked (pending) are filled in as the tasks in PLAN.md complete.

## Problem

| Item | Value |
|---|---|
| Chip | 30 x 30 mm, 100 W uniform heat flux on the underside of the base |
| Base plate | 60 x 60 x 4 mm aluminium (k = 200 W/m-K) |
| Pins | diameter 2-4 mm, pitch/diameter 1.8-2.8, height 20-35 mm, inline or staggered |
| Air | 25 C, duct 60 mm wide, shroud touching the pin tips, 2 / 4 / 6 m/s |
| Outputs | thermal resistance R = (T_chip,max - T_in)/100 W, pressure drop, fin mass |

## Method

1. `src/geometry.py` builds any design as a CadQuery solid and exports STEP + STL.
2. `src/analytic.py` predicts R and dP from the ESDU 73031 and Gaddis-Gnielinski tube-bank
   correlations, pin-fin efficiency, a heat-exchanger (NTU) treatment of the array and the
   Lee et al. spreading-resistance model.
3. `src/make_case.py` writes a complete OpenFOAM 14 case (blockMesh + snappyHexMesh,
   fluid and solid regions coupled with `foamMultiRun`, k-omega SST, steady state).
4. `src/sweep.py` runs the design matrix two cases at a time with time caps; `src/results.py`
   parses each case; `src/analysis.py` produces the Pareto front and figures.
5. `src/surrogate.py` trains an MLP (PyTorch, CUDA) on the sweep with 5-fold CV and searches a
   buildable grid for the lowest R under a pressure-drop budget; the optimum is verified by CFD.
6. `src/visuals.py` renders temperature, speed, pressure and streamlines headlessly.

## Results (pending)

Key figure, Pareto table and validation summary will appear here (see `docs/results.md`,
`docs/mesh_study.md`, `docs/validation.md`, `docs/surrogate.md`).

## How to run

```bash
source /opt/openfoam14/etc/bashrc
make venv && make test          # unit tests (geometry, correlations)
make coarse                     # one coarse CFD case, ~5 min on 6 cores
make sweep && make analysis     # the 36-case sweep (hours) and the Pareto analysis
make surrogate                  # surrogate model + design-space search
```

## Repository

```
src/        geometry, analytic model, case generator, sweep, results, analysis, surrogate, visuals
tests/      pytest acceptance tests for geometry and correlations
docs/       mesh study, validation, results, surrogate, audit (written as tasks complete)
results/    sweep.csv, pareto.csv, surrogate.json
figures/    plots and renders
PLAN.md     task list with acceptance criteria; PROGRESS.md status; DECISIONS.md judgment calls
```

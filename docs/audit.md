# Independent audit (T11)

A fresh reviewer that had not seen the work being produced audited the repository against PLAN.md on 2026-10-13. It edited
no repository files, ran the unit tests and the surrogate re-fit in a scratch copy, and checked every CFD number against the CSV/JSON
files. It could not re-run OpenFOAM or the laptop-only scripts, so CFD results and the T0/T10 logs were checked as recorded, not reproduced.

This page records its verdicts, what was changed in response, and what remains a documented limitation.

## 1. Task-by-task verdicts

| Task | Verdict | Note |
|---|---|---|
| T0 environment | Met (log only) | `docs/env.txt` ends with exit 0; the laptop script was not re-run |
| T1 geometry | Met | 11 tests pass (re-run after the fixes: 11 passed) |
| T2 hand calculation | Met | centre R 0.523/0.378/0.321 K/W, dP 35/155/353 Pa, correct trends |
| T3 CFD case | **Partly not met** | coarse fluid mesh 424k cells (+64k solid) exceeds the 400k target (DECISIONS D10); checkMesh logs and residual history are not kept, so "Mesh OK" and "2 decades" can only be read from flags and final values; Uz ended at 2.1e-3 (PROGRESS previously said 3e-4) |
| T4 mesh independence | **Not met** | fine mesh never solved; the medium-to-fine < 3 % criterion was never measured. Disclosed everywhere |
| T5 validation | Met for the centre design only | R within 5 %, dP within 19 %; 18 of 36 designs are outside +/-30 % in dP |
| T6 sweep | Met, with caveat | 36/36 `ok` only means the solver ran 600 iterations; no case met residualControl |
| T7 analysis | Met | all 46 table rows and the 10-design Pareto set recompute exactly |
| T8 surrogate | Met via the second attempt | first attempt failure is documented |
| T9 visuals | Met | 12 PNGs; colour-bar titles overlap tick labels slightly (not fixed) |
| T10 repo polish | Met on log evidence | fresh-copy `make quick` log exists; reviewer could not re-run it |
| T11 audit | This document | |

## 2. Findings and what was done

### Wrong numbers (fixed)

| Where | Was | Now |
|---|---|---|
| PROGRESS T6 | p residuals > 1e-3 in "15 cases" | 13 of the 36 designs at 4 m/s |
| PROGRESS T6 | interface balance < 0.02 % | 0.009 % max over the 36 designs, 0.021 % over all 56 rows |
| PROGRESS T4 | "R +3.7 %" coarse to medium | R falls 3.7 % |
| README, report, PROGRESS | "equal fin mass (73.6 g)" plate-fin | plate-fin has 76.5 g (4 % heavier); worded as similar mass |
| mesh_study | medium within 1.4 %, coarse 2.5 % of hand calculation | 1.3 % and 2.6 % |
| report section 5 | last Pareto step 7 % lower R | about 8 % (7.6 %) |
| report section 5 | V exponent -0.45 | -0.46 |
| mesh_study | "> 36 min for the fluid mesh" and "exceeded the 60 min cap" | one statement: meshing did not finish within the cap; mesh times not recorded in the CSV |
| DECISIONS D12, report, PROGRESS | two concurrent cases "~4x" slower | roughly 7x |
| DECISIONS D11 | 700 iterations | 600 |
| mesh_study | 14-core laptop | 12 cores, 19 GB |
| PROGRESS T3 | residual U 3e-4 | Uz 2.1e-3 |

### Overstated claims (reworded)

1. **"All converged in temperature."** Replaced everywhere. No case met residualControl; temperature drift was checked only for the centre design; 13 cases have p residual, 4 energy residual and 2 U residual above 1e-3.
2. **Equal-mass plate-fin comparison.** Now "similar mass" with the true masses, and the report states that the plate-fin sink beats several mid-range pin designs on both axes. The mesh level (coarse) is stated.
3. **Surrogate generalisation.** The random-split CV was optimistic. A design-grouped CV was added (`python -m src.surrogate --grouped-only`; result in `results/surrogate_grouped_cv.json`). It reproduced the reviewer's numbers: R^2 0.987 (R) and 0.970 (dP), mean error 2.1 % and 6.8 %, worst case 12 % and 28 %. The README, report and surrogate.md now quote both. The "cross-validation is unchanged" sentence was corrected (dP R^2 0.995 to 0.992).
4. **"Optimum confirmed by CFD."** Reworded as a check of prediction accuracy at one point. The README now states that the CFD dP (153 Pa) is over the 150 Pa budget, that the design sits on the edge of the box (p/d = 1.8, h = 35 mm) with 82.3 g of fins (more than any swept design, max 80.8 g), and that the budget was applied to coarse-mesh dP.
5. **Mesh and uncertainty bounds.** The "+/- 30 %" statements are now described as an observed coarse-to-medium offset on four designs, not a derived bound. "Could not be meshed" became "did not finish within the 60 minute cap".
6. **"Heat balance closed."** Now says the interface balance is satisfied nearly by construction and that the independent air-side balance is 7-9 % high (107-109 W for 100 W) with an untested likely cause.
7. **Validation scope.** README, report and validation.md state that the 30 % criterion holds for the centre design only, that R uses the solid `cellMax`, and that the second-opinion correlation is not independent of the first (the ESDU-labelled constants resemble Zukauskas-type values and were not checked against the ESDU document).
8. **Validation iteration cap.** validation.md now says the 2 and 4 m/s runs stopped at about 515 iterations (status `timeout`).

### Repository consistency (fixed)

- Stale "no prism layers" text removed from `src/studies.py` (the validation generator now emits the corrected discussion and caveats), `results/T5/validation.md` and DECISIONS line 25 (marked superseded).
- `src/sweep.py` docstring and defaults now match the Makefile (coarse, 8 processes, 1 job, 600 iterations).
- `src/surrogate.py` docstring no longer mentions a non-existent `--verify-out`; `results/surrogate.json` architecture string now says 7 inputs; the docstring says the parity figure and `docs/surrogate.md` were made by hand.
- PROGRESS T10 stale text corrected; `requirements.txt` notes torch as optional; stray `log.cht` removed; `figures/validation.png` is now referenced from validation.md; README lists the extra result folders and this audit.

## 3. Open items (documented, not fixed)

- T3 mesh above 400k cells and T4 medium-to-fine criterion: not met; a fine-mesh run is not feasible on this laptop.
- No residual histories or checkMesh logs are stored for the sweep.
- T8 used a grid search rather than scipy optimisation (disclosed in DECISIONS/surrogate.md).
- `docs/surrogate.md` and `figures/surrogate_parity.png` are not regenerated by `make surrogate`; the star on the Pareto figure is tied to the d3.7 result file.
- Hard-coded Windows mirror paths in `src/sweep.py` and `jobs/`.
- `PLAN.md` was edited by the loop despite the rule; the medium-mesh centre run (59.7 min) exceeded the 45 minute solver rule; no duct or chip STLs; the report is longer than two pages.
- Colour-bar titles overlap tick labels in the renders; the Pareto labels crowd the points; the `solid_T` pin sides look uniformly grey in at least one render.
- Plate-fin comparison and V-scaling are not in `docs/results.md`.
- Nothing was compared with physical measurements.

## 4. Checks after the fixes

- `pytest`: 11 passed.
- Grouped CV re-run: matches the reviewer's figures.
- Text scan for "equal mass", "all converged", "4x", "14-core" and "could not be meshed" finds no remaining occurrences.
- The laptop copy of the repository was brought in line with the cloud copy after these edits (see PROGRESS.md).

# Surrogate model (T8)

A small neural network predicts thermal resistance R and pressure drop dP from the design variables, so a design can be evaluated in microseconds instead of 3-7 minutes of CFD (coarse mesh).

- **Training data:** 56 coarse-mesh CFD cases (36 designs at 4 m/s, plus 10 designs at each of 2 and 6 m/s).
- **Model:** MLP with two hidden layers of 32 tanh units, trained with Adam for 3000 epochs on log R and log dP, on the RTX 5070 (CUDA, about 40 s per fit).
- **Validation:** 5-fold cross-validation, then one real CFD case at the predicted optimum.
- **Optimisation:** exhaustive search on a buildable grid (d in 0.1 mm steps, p/d in 0.05 steps, h in 1 mm steps, both layouts; 14,112 designs) for the lowest R with predicted dP <= 150 Pa at 4 m/s.

## Attempt 1: raw design variables only (failed the 15 % check)

Inputs d, p/d, h, layout, V. Cross-validation looked excellent (R^2 0.994 for R, 0.995 for dP; mean absolute error 1.6 % for R, 4.1 % for dP), so the model fit the sweep well. The predicted optimum was d = 3.3 mm, p/d = 1.85, h = 35 mm, inline (R 0.339 K/W, dP 148 Pa).

The verification CFD case gave R = 0.381 K/W and dP = 109 Pa:

| | predicted | CFD | error |
|---|---|---|---|
| R (K/W) | 0.339 | 0.381 | +12 % |
| dP (Pa) | 147.7 | 109.2 | -26 % |

dP missed the 15 % target. Cause: the number of pins is an integer, and it jumps with d and p/d. d = 3.3, p/d = 1.85 gives 81 pins in 9 rows, whereas the sweep has 121 pins (d = 3, p/d = 1.8) and 64 pins (d = 4, p/d = 1.8). The sweep sits on a coarse 3 x 3 grid in (d, p/d), so a smooth function of d and p/d interpolates across those jumps. Cross-validation could not reveal this, because every fold point lies on the same grid.

## Attempt 2: added geometry features (passed)

Two inputs computed by the geometry generator were added: the number of pin rows along the flow, and the log of the total wetted pin area. With these, the verification point from attempt 1, held out of training, is predicted to R 0.365 K/W (4 % off) and dP 115.5 Pa (6 % off). Cross-validation is unchanged (R^2 0.996 for R, 0.992 for dP; mean absolute error 1.5 % and 4.5 %).

The retrained model's optimum is d = 3.7 mm, p/d = 1.8, h = 35 mm, inline. A new CFD case at that design gave:

| | predicted | CFD | error |
|---|---|---|---|
| R (K/W) | 0.341 | 0.340 | -0.3 % |
| dP (Pa) | 143.4 | 153.0 | +6.7 % |

Both are inside the 15 % target. The real pressure drop (153 Pa) is 2 % above the 150 Pa budget, so the budget was met by the prediction but not quite by the verification case.

## What the optimum buys

Compared with the nearest swept designs at 4 m/s (inline, p/d = 1.8, h = 35 mm), the surrogate optimum has lower R than d = 4 mm (0.369 K/W at 117 Pa) and about 25 % lower pressure drop than d = 3 mm (0.316 K/W at 203 Pa), filling the gap between them.

## Limits

- The model was trained on coarse-mesh CFD. Medium-mesh dP is about 25 % lower than coarse (docs/mesh_study.md), so absolute dP values carry that offset; the trends and the ranking of designs are what the model captures.
- Only the 10 best designs were simulated at 2 and 6 m/s, so the velocity dependence is learned from a subset of the design space; the optimum is reported at 4 m/s only.
- With 56 points, the design space is sparsely sampled; the verification case is the evidence that the optimum is real, not the cross-validation score alone.
- The first attempt is kept here deliberately: a good cross-validation score did not guarantee a good prediction between grid points.

Files: results/T8/ (attempt 1), results/T8b/ (attempt 2), figures/surrogate_parity.png.

# Pin-fin heat sink optimisation: CAD, conjugate-heat-transfer CFD and a GPU surrogate

Griffin, October 2026. Repository: heatsink-cfd.

## 1. Problem

An air-cooled pin-fin heat sink must remove 100 W from a 30 x 30 mm chip mounted under a
60 x 60 x 4 mm aluminium base plate, in a 60 mm wide duct whose shroud touches the fin tips.
The design question is the classic thermal-hydraulic trade-off: more and thinner pins lower the
thermal resistance but raise the pressure drop the fan must supply. Design variables are the
pin diameter d (2-4 mm), the pitch-to-diameter ratio p/d (1.8-2.8), the pin height h (20 or
35 mm) and the layout (inline or staggered); the inlet velocity is 4 m/s for the sweep.

Figures of merit: thermal resistance R = (T_chip,max - T_inlet) / 100 W, pressure drop dP
between duct inlet and outlet, and fin mass.

## 2. Method

**Geometry.** Every design is generated parametrically with CadQuery (`src/geometry.py`) and
exported as STEP (for CAD) and STL (for meshing). Pins are placed on a square grid centred on the
base; staggered arrays shift alternate rows by half a pitch.

**Hand calculation.** Before any CFD, `src/analytic.py` estimates R and dP from established
correlations: ESDU 73031 for the array heat-transfer coefficient (continuous in Reynolds number,
with the Zukauskas/Bejan correlation as a second opinion), Gaddis and Gnielinski (1985) for the
bank pressure drop, adiabatic-tip pin-fin efficiency, a heat-exchanger (NTU) treatment of the
array so the air temperature rise is accounted for, and the Lee et al. (1995) closed form for the
spreading resistance from the 30 mm chip into the 60 mm base.

**CFD.** `src/make_case.py` builds an OpenFOAM 14 case. The fluid and the solid are meshed
separately (blockMesh background, snappyHexMesh refinement on the pins, four prism layers on the
fluid side of every pin and the base) and coupled through non-conformal couples
(`createNonConformalCouples`) in a `foamMultiRun` conjugate-heat-transfer run. The fluid is air
as a perfect gas with the k-omega SST model, steady state; the solid is aluminium
(k = 200 W/m-K). The chip applies a uniform 111 kW/m2 heat flux (fixedGradient on the chip
patch), the sides are symmetry planes, the shroud and floor are adiabatic no-slip walls.
On the stitched pin/base interface `omegaWallFunction` diverged, so that patch uses
`omega zeroGradient` with `nutUSpaldingWallFunction` and `kqRWallFunction` (DECISIONS.md D9);
all other walls use `omegaWallFunction`. Each sweep case runs 600 iterations on 8 cores, one case
at a time (two concurrent cases were 4x slower each, DECISIONS.md D12), 2-16 minutes per case.

**Verification and validation.** The mesh independence study (Section 3) runs the centre design
on three refinement levels; the validation (Section 4) compares CFD with the hand calculation at
three velocities.

**Surrogate model.** A small MLP (two hidden layers of 32 tanh units) trained in PyTorch on the
RTX 5070 predicts log R and log dP from the design variables plus two geometry features (pin rows
along the flow and wetted pin area). It is evaluated with 5-fold cross-validation and then
used to search a buildable grid (0.1 mm in d, 0.05 in p/d, 1 mm in h, both layouts) for the lowest
R under a 150 Pa budget at 4 m/s; the predicted optimum is checked with one more CFD run.

## 3. Mesh independence

Centre design (d = 3 mm, p/d = 2.2, h = 35 mm, staggered) at 4 m/s on three meshes.

| mesh | fluid cells | R K/W | dP Pa | note |
|---|---|---|---|---|
| coarse | 0.42 M | 0.387 | 143 | converged |
| medium | 1.77 M | 0.373 | 107 | stopped at the 60 min cap, residuals ~1e-4 |
| fine | 7.6 M | n/a | n/a | meshing exceeded the 60 min cap |

Thermal resistance changes 3.7 % from coarse to medium; pressure drop changes 25 %. The
fine mesh could not be run on this laptop, so mesh independence is **not demonstrated**: the
plan's medium-to-fine criterion (< 3 %) is not met. dP is not converged (medium is 31 % below the correlation for the centre design) and R is only
mesh-insensitive for dense arrays (see below). The 36-design sweep therefore ran on
the coarse mesh, and its absolute dP values should be read as +/- 30 %. Three more designs were re-run on the medium mesh (about 45 minutes each, same 600 iterations) to see how the coarse-mesh results shift:

| design (4 m/s) | R coarse | R medium | change | dP coarse Pa | dP medium Pa | change | dP hand Pa |
|---|---|---|---|---|---|---|---|
| d3.7, pd1.8, h35, inline | 0.340 | 0.336 | -1.2 % | 153 | 116 | -24.2 % | 131 |
| d3, pd2.2, h35, inline | 0.418 | 0.407 | -2.6 % | 85 | 66 | -22.2 % | 64 |
| d4, pd2.8, h35, inline | 0.796 | 0.707 | -11.1 % | 24 | 23 | -4.3 % | 22 |

The offset is **not uniform**. For the two denser arrays the medium mesh gives 22-24 % lower dP and 1-3 % lower R, and the medium dP lands close to the hand calculation (66 vs 64 Pa, 116 vs 131 Pa). For the sparsest array dP barely moves (-4 %) but R drops 11 %, so the coarse mesh over-predicts the resistance of sparse, large-pin designs. The ordering of these three designs is the same on both meshes, but the coarse sweep slightly understates how good sparse designs are and overstates the pressure drop of dense ones, so the Pareto front would shift somewhat on a finer mesh.

## 4. Validation against hand calculations

The centre design on the coarse mesh at 2, 4 and 6 m/s, against the hand calculation:

| V m/s | R CFD | R hand | dP CFD Pa | dP hand Pa |
|---|---|---|---|---|
| 2 | 0.521 | 0.523 | 41 | 35 |
| 4 | 0.387 | 0.378 | 143 | 155 |
| 6 | 0.337 | 0.321 | 303 | 353 |

R agrees within 5 % and dP within 19 % (target: 30 %). Across the whole 36-design sweep the
CFD/hand ratio is 1.00-1.13 for R (mean 1.06) but 0.60-2.57 for dP (mean 1.27): the tube-bank
pressure-drop correlation is reliable for the centre design but not for short, confined
arrays with few rows, and the CFD includes the 4 mm base step and the shroud contact that the
correlation does not. The heat balance is closed to the chip power through the fluid-solid
interface (largest error 0.009 % at 4 m/s).

## 5. Results of the 36-design sweep

All 36 designs ran and converged in temperature at 4 m/s (coarse mesh, 600 iterations). In 13
of them the pressure residual stayed above 1e-3 (largest 3.8e-3), so their dP carries extra
uncertainty. Thermal resistance spans 0.274 to 0.997 K/W and pressure drop 24 to 781 Pa; 10 of
the 36 designs are Pareto-optimal (figures/pareto.png, full table in docs/results.md).

| d mm | p/d | h mm | layout | fin mass g | R K/W | dP Pa |
|---|---|---|---|---|---|---|
| 4 | 2.8 | 35 | inline | 29.7 | 0.796 | 24 |
| 3 | 2.2 | 35 | inline | 54.1 | 0.418 | 85 |
| 4 | 1.8 | 35 | inline | 76.0 | 0.369 | 117 |
| 3 | 1.8 | 35 | staggered | 77.5 | 0.296 | 290 |
| 2 | 1.8 | 35 | staggered | 73.6 | 0.274 | 667 |

- Tall pins (35 mm) dominate: every Pareto design has h = 35 mm.
- Along the Pareto front, going from the lowest-dP to the lowest-R design lowers R by a factor of 2.9
  and raises dP by a factor of 28; the last step (0.296 to 0.274 K/W, 7 % lower R) costs 2.3 times the
  pressure drop.
- Staggering lowers R by 2-9 % (mean 6 %) at the same d, p/d and h and raises dP by 16-84 % (mean 52 %).
- Across 2, 4 and 6 m/s, R scales as about V^-0.45 and dP as about V^1.8 for the ten designs that
  were run at all three speeds.

## 6. Surrogate model and design-space search

The network was trained on 56 coarse CFD cases (36 designs at 4 m/s plus 10 designs at each of 2 and
6 m/s). 5-fold cross-validation: R^2 = 0.996 (R) and 0.992 (dP), mean absolute error 1.5 % and 4.5 %.

**The first attempt failed its verification check.** With only d, p/d, h, layout and V as inputs, the
predicted optimum (d = 3.3 mm, p/d = 1.85) was off in CFD by +12 % in R and -26 % in dP. The number of
pins is an integer that jumps with d and p/d (121, 81 and 64 pins at neighbouring designs), and the
sweep's 3 x 3 grid in (d, p/d) cannot reveal that to a smooth model. Adding pin rows and wetted area
as inputs fixed it: the held-out failed case is then predicted within 6 %. The retrained model's
optimum under a 150 Pa budget is d = 3.7 mm, p/d = 1.8, h = 35 mm, inline:

| | surrogate | CFD | error |
|---|---|---|---|
| R K/W | 0.341 | 0.340 | -0.3 % |
| dP Pa | 143.4 | 153.0 | +6.7 % |

Both are within the 15 % target; the real pressure drop is 2 % above the 150 Pa budget.

## 7. Equal-mass comparison with a plate-fin heat sink

A straight plate-fin sink with the same fin mass (73.6 g: nine 1.5 mm plates, 35 mm tall) as the
lowest-R pin design, same base, same duct and flow: R = 0.379 K/W at 29 Pa, against 0.274 K/W at
667 Pa for the pin array. The pin array is 28 % lower in thermal resistance, the plate-fin sink needs
23 times less pressure. Pin fins win on cooling per unit mass; plate fins win when the fan is the limit.
Only one plate-fin design was simulated, so this is a data point rather than an optimised comparison.

## 8. Limitations

- Steady RANS (k-omega SST) with four prism layers on the pins; the flow around pins at
  Re ~ 700-2500 is unsteady in reality, so the steady solution is a time-mean surrogate.
- The stitched pin/base interface uses `omega zeroGradient` instead of a wall function because
  `omegaWallFunction` diverged there; near-pin turbulence is therefore approximate.
- No mesh-independence proof: the fine mesh could not be run, and pressure drop changes 25 % from
  coarse to medium. Treat absolute dP as +/- 30 %; rankings and trends are what the study supports.
- Pins of 2 mm are only a few cells across on the coarse mesh.
- Correlation uncertainty is itself 15-25 %; agreement within 30 % is the realistic target.
- The surrogate was trained on 56 cases on a coarse grid in (d, p/d) and verified at one design.
- The duct side walls are symmetry planes and the shroud touches the fin tips; a real assembly
  would have a tip gap and wall friction.
- No contact resistance between chip and base; uniform chip heat flux.

## 9. Conclusions

For a 100 W chip in a 4 m/s shrouded duct, a 35 mm tall pin array of 3.7 mm pins at p/d = 1.8
(inline) reaches R = 0.34 K/W, a chip rise of 34 K, at 153 Pa (coarse mesh); the 2 mm
staggered array gets down to 0.27 K/W but at four times the pressure drop. CFD agrees with the hand
calculation within 5 % in R and 19 % in dP for the centre design, the surrogate predicts held-out
designs to 1.5 % in R on average, and its optimum was confirmed by CFD. What is not established: grid
convergence of dP (fine mesh not run) and any comparison with measurements.

## Resume bullets

- Built a parametric pin-fin heat sink pipeline (CadQuery, OpenFOAM 14 conjugate heat transfer, PyTorch) and simulated 36 designs plus 20 velocity variants; CFD thermal resistance matched hand calculations within 5 % and pressure drop within 19 % on the validation design.
- Trained a GPU surrogate (RTX 5070) on the CFD sweep (5-fold CV R^2 0.996) to search the design space; diagnosed a failed first optimum (pin-count discretisation), fixed it with geometry features, and confirmed the new optimum in CFD within 0.3 % in R and 7 % in dP.
- Found that pin arrays beat an equal-mass plate-fin sink by 28 % in thermal resistance at 23x the pressure drop, and documented the mesh-sensitivity and turbulence-model limits of the study.

## References

- ESDU 73031, Convective heat transfer during crossflow of fluids over plain tube banks.
- Gaddis, E. S., Gnielinski, V., Pressure drop in cross flow across tube bundles, Int. Chem. Eng. 25 (1985) 1-15.
- Zukauskas, A., Heat transfer from tubes in crossflow, Adv. Heat Transfer 8 (1972); constants as tabulated by Bejan.
- Lee, S., Song, S., Au, V., Moran, K. P., Constriction/spreading resistance model for electronics packaging, ASME/JSME Thermal Eng. Conf. (1995).
- OpenFOAM Foundation, OpenFOAM 14 tutorials multiRegion/CHT (heatedDuct, circuitBoardCooling, coolingSphere).

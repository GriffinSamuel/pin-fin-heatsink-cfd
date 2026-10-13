# Pin-fin heat sink optimisation: CAD, conjugate-heat-transfer CFD and a GPU surrogate

Griffin, October 2026. Repository: heatsink-cfd.

> Draft. Values marked {{...}} are filled from results/ when the corresponding task completes.

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

**CFD.** `src/make_case.py` builds an OpenFOAM 14 case: a nine-block background mesh (3 mm
cells, the chip footprint as its own patch), snappyHexMesh refinement on the pins, and
splitMeshRegions into a fluid and a solid region coupled through `foamMultiRun`. The fluid is
air as a perfect gas with the k-omega SST model, steady state; the solid is aluminium
(k = 200 W/m-K). The chip applies a uniform 111 kW/m2 heat flux (fixedGradient on the chip
patch), the sides are symmetry planes, the shroud and floor are adiabatic no-slip walls. Each
case runs on 6 cores; the sweep runs two cases at a time with time caps and is resumable.

**Verification and validation.** The mesh independence study (Section 3) runs the centre design
on three refinement levels; the validation (Section 4) compares CFD with the hand calculation at
three velocities.

**Surrogate model.** A small MLP (5-32-32-2, tanh) trained in PyTorch on the RTX 5070 predicts
log R and log dP from (d, p/d, h, layout, V). It is evaluated with 5-fold cross-validation and then
used to search a buildable grid (0.1 mm in d, 0.05 in p/d, 1 mm in h, both layouts) for the lowest
R under a pressure-drop budget; the predicted optimum is checked with one more CFD run.

## 3. Mesh independence

{{mesh_study}}

## 4. Validation against hand calculations

{{validation}}

## 5. Results of the 36-design sweep

{{results}}

## 6. Surrogate model and design-space search

{{surrogate}}

## 7. Equal-mass comparison with a plate-fin heat sink

{{plate}}

## 8. Limitations

- Steady RANS (k-omega SST) with wall functions and no prism layers on the pins; the flow around
  pins at Re ~ 700-2500 is unsteady in reality, so the steady solution is a time-mean surrogate.
- Correlation uncertainty is itself 15-25 %; agreement within 30 % is the realistic target.
- The duct side walls are symmetry planes and the shroud touches the fin tips; a real assembly
  would have a tip gap and wall friction.
- No contact resistance between chip and base; uniform chip heat flux.

## 9. Conclusions

{{conclusions}}

## Resume bullets

{{bullets}}

## References

- ESDU 73031, Convective heat transfer during crossflow of fluids over plain tube banks.
- Gaddis, E. S., Gnielinski, V., Pressure drop in cross flow across tube bundles, Int. Chem. Eng. 25 (1985) 1-15.
- Zukauskas, A., Heat transfer from tubes in crossflow, Adv. Heat Transfer 8 (1972); constants as tabulated by Bejan.
- Lee, S., Song, S., Au, V., Moran, K. P., Constriction/spreading resistance model for electronics packaging, ASME/JSME Thermal Eng. Conf. (1995).
- OpenFOAM Foundation, OpenFOAM 14 tutorials multiRegion/CHT (heatedDuct, circuitBoardCooling, coolingSphere).

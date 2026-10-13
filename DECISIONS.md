# Decisions (judgment calls made while executing PLAN.md)

- 2026-10-12 Shroud instead of bypass: the duct top is placed at the pin tips (duct height =
  base_t + h) rather than 10 mm above them. A 10 mm bypass would make the hand calculation
  unreliable (flow split between array and bypass is not captured by 1-D correlations) and
  adds mesh. Fully shrouded pin-fin arrays are the standard configuration in the pin-fin
  literature. PLAN.md updated accordingly.
- 2026-10-12 The base plate sits on the duct floor as a 4 mm step (not flush), which is how a
  heat sink mounted on a board actually protrudes. The step loss is not in the hand calc.
- 2026-10-12 Chip heat input is applied as a fixed heat flux on a dedicated blockMesh patch
  (the floor under the chip footprint) using a fixedGradient temperature condition
  (dT/dn = q''/kappa, exact for constant kappa). OpenFOAM 14 no longer ships the
  externalWallHeatFluxTemperature condition, and this avoids a third region.
- 2026-10-12 Duct side walls are symmetry planes (frictionless, adiabatic) so the 60 mm wide
  duct does not add wall friction that the correlations do not include.
- 2026-10-12 Case structure copied from OpenFOAM-14 tutorials multiRegion/CHT/heatedDuct
  (meshing and region splitting), circuitBoardCooling (steady-state settings) and
  coolingSphere/templates (air, aluminium, k-omega SST boundary conditions). No buoyancy
  (no p_rgh field; forced convection at 2-6 m/s).
- 2026-10-12 Aluminium kappa = 200 W/m-K in both the CFD and the hand calculation.
- 2026-10-12 Hand calculation uses ESDU 73031 for Nu (continuous across Re) with the
  Zukauskas/Bejan constants reported as a second estimate, and Gaddis-Gnielinski (1985) for
  pressure drop. The Gaddis-Gnielinski blending term was verified against the TORCHE
  reference implementation after a web source rendered it incorrectly.
- 2026-10-12 (SUPERSEDED by the decision below on separate region meshes with prism layers) No prism layers on the pins yet (addLayers false, like the heatedDuct tutorial);
  wall functions handle the near-wall region. To be revisited if the mesh study shows
  sensitivity.
- 2026-10-12 Local development uses OpenFOAM v1912 (ESI) in the cloud workspace for mesh
  testing only (flavour "esi" in make_case.py); all solver runs use OpenFOAM 14 on the laptop.
- 2026-10-12 Local solver check: the coarse centre-design mesh was run with plain simpleFoam
  (laminar, incompressible, OpenFOAM v1912) as a mesh/physics sanity check: converging,
  inlet-outlet pressure drop ~175 Pa (correlation 155 Pa), max speed 21 m/s, all plausible.
  A v1912 chtMultiRegionSimpleFoam translation of the case diverged at the second iteration
  (fluid enthalpy); since that solver and its dictionaries differ from OpenFOAM 14's fluid
  solver, the translation was abandoned rather than debugged. The OpenFOAM 14 settings follow
  the circuitBoardCooling tutorial: U initialised to the inlet velocity, relaxation
  U 0.3 / h 0.7 / k,omega 0.3 / p 0.7, upwind for k and omega, 2nd-order for U and h.
- 2026-10-12 First OpenFOAM-14 run (coarse mesh, centre design): everything executes and
  balances (99.9 W in through the chip, 99.9 W out through the interface, dP 137 Pa vs 155 Pa
  from the correlation) but R = 0.70 K/W against 0.38 K/W predicted. The y+ on the pins is
  ~6 (buffer layer) and the first cell is 0.75 mm, so the near-wall heat transfer is limited by
  conduction across the first cell rather than resolved. Decision: mesh each region separately
  (heat sink surface as a wall patch), add prism layers on the fluid side, and couple the two
  meshes with createNonConformalCouples exactly as the OpenFOAM-14 hotWire tutorial does.
  The single-mesh cellZone/splitMeshRegions route cannot add layers (OpenFOAM-14 layer
  addition is patch-based only).

## D9 (2026-10-12) Interface turbulence BC
omegaWallFunction on the non-conformally stitched pin/base interface (197k fragment faces) makes omega diverge
(1e44 within 20 iterations; confirmed by variants: omega zeroGradient + kqRWallFunction + nutUSpaldingWallFunction
on the interface is stable, omegaWallFunction is not, regardless of blended). Decision: interface omega zeroGradient,
k kqRWallFunction, nut nutUSpaldingWallFunction (continuous), alphat wallFunction. Other walls keep omegaWallFunction (blended).
Consequence: near-pin turbulence is approximate; validated against correlations (docs/validation.md).

## D10 (2026-10-12) Coarse mesh size
The coarse level (surface refinement 2 plus 4 prism layers) gives 424k fluid + 64k solid cells (0.49M), above the
<400k target in PLAN.md. Accepted: the extra cells are the prism layers, which are needed for y+ of 1-5 at the pins;
the mesh study (T4) reports the true counts. Solve time 200 s per 400 iterations on 6 cores is well within budget.

## D11 (2026-10-13) Sweep mesh level
Mesh study: coarse 0.49M cells (13 min solve), medium 2.2M (60 min, hit the cap), fine 9.7M (meshing did not finish within the 60 min cap, abandoned).
R changes 3.7 % coarse to medium, dP 25 %. PLAN's medium-to-fine < 3 % criterion cannot be met on this hardware; recorded
as a limitation, not hidden. Sweep runs on the coarse mesh with 600 iterations (validation about 515 to 1500) (T_max moves < 0.03 K between
400 and 1500 iterations on the centre case). Key designs are re-run on medium afterwards to report the dP offset.

## D12 (2026-10-13) One case at a time
Two concurrent 6-process cases each ran roughly 7x slower than a solo case (519 iterations in 30 min vs ~0.5 s/iteration solo),
so throughput was worse than sequential. The sweep runs 1 case at a time with 8 processes and 600 iterations (the centre
case is converged to 0.03 K by 400 iterations). PLAN.md's "2 cases at a time" was based on a benchmark of a different case size.

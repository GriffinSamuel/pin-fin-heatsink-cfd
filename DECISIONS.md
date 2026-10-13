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
- 2026-10-12 No prism layers on the pins yet (addLayers false, like the heatedDuct tutorial);
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

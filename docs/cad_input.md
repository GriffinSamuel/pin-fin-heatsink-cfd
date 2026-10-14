# Running the simulation on your own CAD file

```bash
python -m src.run --inspect my_sink.step                      # measurements and a top-view picture, nothing is run
python -m src.run --cad my_sink.step --chip 30x30 --power 100 --V 4 --out results/cad/my_sink
python -m src.run --cad-dir sinks/ --chip 30x30 --power 100 --V 4 --out results/cad/batch
python -m src.run --cad my_sink.step --dry-run                # write the case only (no mesher, no solver)
```

The tool imports a STEP (`.step`, `.stp`) or STL file of one heat sink, orients and measures it, builds the same
two-region OpenFOAM 14 conjugate case the study used, runs it, and reports R, hottest solid temperature, pressure
drop, fin mass and the interface heat balance. A folder becomes a table (`sweep.csv`), a Pareto set
(`pareto.csv`, `pareto.png`) and `results.md`. CFD needs OpenFOAM 14 (the laptop job runner); `--inspect` and `--dry-run`
need only Python.

## What the tool assumes about the part

- One solid body, closed surface. STEP files with several solids and STL files with several shells are refused.
  A hole of a few triangles in an STL is filled once; anything larger is refused.
- A base plate with fins standing on it. The base thickness is found by taking horizontal sections and noting where the
  section area drops to under 0.6 of the base area. A block with no fins is refused ("no fins found").
- Units are taken from the size of the part (extent under 1 gives metres, 10 to 2000 gives millimetres) and can be forced with
  `--units mm|m|in`; a part under 10 mm across draws a warning that it may be inches.
- The coordinate frame used by the case is x = flow, y = span, z = up. The base lies on the duct floor, the fin tips touch the
  duct top (the shroud, as in the study), and the duct runs one base length upstream of the base and two downstream of it.
- Orientation is automatic: the largest flat face is put down, and if the fins are plates whose broad faces face the flow the part
  is turned 90 degrees about z ("rotated 90 degrees about z" is then listed as a warning). Override with `--orient "x90 z-90"`
  (rotations in degrees about x, y, z in the order given) or `--orient none`.
- The chip is a rectangle on the floor under the base, centred plus `--chip-offset dx,dy` (mm). A chip that leaves the
  base is refused.
- Material: aluminium (200 W/m-K, 2700 kg/m3) or copper (385, 8960) with `--material`; fin mass uses the same density.

## What is done to the geometry

The part is exported to a clean STL (`<stem>_clean.stl`, mm) and a second STL for snappyHexMesh (`<stem>_snappy.stl`, metres).
The second is the sink extended 1 mm below the floor, 1 mm past the side walls and 1 mm above the shroud, so that no STL face
lies on a boundary of the background mesh (the same embedding the study's own geometry uses). If the fin tips are not flat
(pointed pins, say), the 1 mm extension is impossible; the tool then leaves a 0.3 mm gap between tip and shroud and warns.
That gap lets air bypass the fins, so such results are lower in pressure drop than a sealed shroud would give.

## Mesh level

The surface refinement is chosen from the thinnest fin so that about 2.5 cells span it at the coarse level
(`level = clamp(ceil(log2(cell / (min_feature / 2.5))), 2, 4)`, cell = 3 mm). The study's 2 mm pins and 1.5 mm plates get levels 2 and 3.
`--mesh medium` adds one level and `fine` two. `--surf-level N` overrides. The importer prints a warning at level 4 because the
mesh becomes large.

## Outputs

`out/<stem>_V<V>_<mesh>/` holds one case each (`case.json`, `results.json`, the OpenFOAM folders and logs).
`results.json` has the usual fields plus the measured model under `"model"`. Interrupted runs resume (a case with a temperature
result is skipped).

Exit codes: 0 ok, 2 input refused (the message says why), 3 meshing failed (see `log.Allmesh`), 4 solver failed or hit its cap.

## What is and is not validated

- There is no hand calculation and no surrogate for arbitrary shapes. Values are CFD only, at the mesh level named.
- Everything in the study's limitations still holds: the mesh-independence criterion was not met, no case met its residual
  criterion, the air-side energy balance reads 7 to 9 % high, and nothing was compared with measurements.
- The only check of the new path is a back-to-back comparison: the study's centre pin design and its plate-fin design, exported
  as STEP files and run through this path, against the study's own results (see the acceptance record in PROGRESS.md, T12).
  That shows the path reproduces the study for those two shapes; it does not validate other shapes.
- Not supported: several bodies, fins on both sides of the base, ducts that are not rectangular, flow around the sink instead of
  through a shroud, radiation, temperature-dependent conductivity, multiple chips.

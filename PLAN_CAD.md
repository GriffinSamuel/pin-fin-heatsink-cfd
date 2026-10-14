# PLAN_CAD: run the CHT simulation on any heat sink CAD file

Branch: `cad-input` (created from master after T11). master holds the finished pin-fin study and must
not change. Everything below is additive: new modules, a new CLI, new tests, new docs. The 36-design
study must still reproduce exactly (see the regression tests in step 7).

This plan was written after reading the code; the file/line references are current as of commit
`788aecf`. Follow it in order. Each step ends with a checkpoint that must pass before the next step.

## 0. What the tool is

```
python -m src.run --cad my_sink.step --chip 30x30 --power 100 --V 4 --out results/cad/my_sink
python -m src.run --cad-dir sinks/   --chip 30x30 --power 100 --V 4 --out results/cad/batch
python -m src.run --inspect my_sink.step            # measurements + top-view PNG, no case written
```

Given a STEP or STL of a heat sink (base plate plus fins of any shape), the tool orients it, measures
it, builds the same two-region OpenFOAM 14 conjugate case the study used (duct sized from the sink,
chip patch under the base, shroud touching the fin tips), runs it, and reports R, chip temperature,
dP and fin mass. A folder of files becomes a sweep table and a Pareto front. There is no hand
calculation and no surrogate for arbitrary shapes; the output says so.

The parametric generator (`src/geometry.py`) stays as it is and becomes one way to produce input
files for this tool.

## 1. Current coupling between geometry and case (what has to change)

Hard-coded today, all in metres unless noted:

| where | what | value |
|---|---|---|
| `src/make_case.py:30-38` | `T_IN`, `Q_CHIP`, `KAPPA_AL`, `X_SPLITS`, `Y_SPLITS`, `BASE_CELL`, `NX`, `NY` | 298.15 K, 100 W, 200, chip at x 0.015-0.045 / y 0.015-0.045, duct x -0.060..0.180, y 0..0.060, 3 mm cells |
| `make_case.py:157,161` | snappy inside points | fluid (-0.0305, 0.0305, H/2+0.0004); solid (0.0305, 0.0305, 0.0021) |
| `make_case.py:182,188` | refinementBox / pinBox | x -0.012..0.085, y -0.001..0.061; pinBox x -0.003..0.066, z from 0.003 |
| `make_case.py:711-716` | hydraulic diameter, chip flux | duct width 0.060, chip 0.03 x 0.03 |
| `make_case.py:FUNCTIONS` | function objects | patch names `chip`, `inlet`, `outlet`, `heatsink` (keep these names) |
| `src/geometry.py:24-29` | `BASE_L/W/T`, `CHIP`, `MARGIN`, `EMBED` | 60, 60, 4, 30, 1.5, 1.0 mm |
| `geometry.py:117-126` | `make_heatsink_for_snappy` | the STL for snappy is the sink extended 1 mm below the floor, 1 mm beyond both side walls and 1 mm above the shroud, so no STL face lies on a blockMesh boundary. This embedding is the one thing an imported CAD does not have and must be reconstructed (step 3). |
| `src/results.py:16-17` | `T_IN`, `Q_NOMINAL` | used when the chip flux integral is missing |
| `src/studies.py:run_one`, `src/sweep.py:run_one` | case name `f"{spec.name}_V{V:g}_{mesh}"`, `write_case(spec, ...)` | the runner API takes a `HeatSinkSpec` |

Mesh refinement: `MESH_LEVELS` coarse surf=2 means 3 mm / 2^2 = 0.75 mm cells on the sink surface,
plus 4 prism layers (`--layers`). The 2 mm pins are ~2.7 cells across at coarse. The plate-fin
comparison ran t = 1.5 mm plates at the same level.

Local mesher: the cloud workspace has OpenFOAM v1912 (ESI) at `/usr/bin/blockMesh`,
`/usr/bin/snappyHexMesh` (`source /usr/share/openfoam/etc/bashrc` is not needed; the binaries run
directly). `write_case(..., flavour="esi")` writes a case whose `Allmesh` meshes both regions
(no non-conformal coupling, meshing only). `work/cases/test_esi_coarse` is a worked example:
solid 66,576 cells there against 64,132 with OpenFOAM 14 on the laptop, so cross-version counts agree
to a few percent. Use this for all mesh tests in the cloud. Solving only happens on the laptop
(OpenFOAM 14 in WSL, job runner: see section 9).

## 2. New module `src/cad_import.py`

Dependencies to add to `requirements.txt`: `shapely`, `manifold3d` (trimesh boolean engine). trimesh
5.1 and cadquery 2.8 are installed in the cloud venv already.

```python
@dataclass
class SinkModel:
    source: str                 # original file path
    units_in: str               # "mm" | "m" | "in", detected or given
    transform: list[list[float]]  # 4x4 applied to the input (rotation + translation), for the report
    L: float; W: float; base_t: float; h: float      # mm, in the oriented frame (x flow, y span, z up)
    footprint: list[list[float]]  # base outline polygon at z = base_t/2, mm (for the top-view figure)
    fin_sections: list[list[list[float]]]  # fin outline polygons at z = base_t + h/2, mm
    min_feature_mm: float       # min(min fin thickness, min fin gap)
    volume_mm3: float; fin_volume_mm3: float; wetted_area_mm2: float
    n_fins: int                 # number of fin polygons in the mid-height section
    clean_stl: str              # oriented sink in mm, no embedding (deliverable / renders)
    snappy_stl: str             # oriented, embedded, in METRES (for the mesher)
    warnings: list[str]

def load(path, units="auto", orient="auto", out_dir=None) -> SinkModel
def inspect_figure(model, png_path)          # top view: footprint, fin sections, chip rectangle later
```

### 2.1 Loading

- `.step/.stp`: `cq.importers.importStep(path)`. If the result has more than one solid: refuse with
  "file contains N solids; export the heat sink as one body" (no `--union` option in v1; keep it
  simple). Tessellate to STL with `cq.exporters.export(..., tolerance=0.02, angularTolerance=0.1)`
  (the same tolerance `geometry.py:export_all` uses) and continue as STL.
- `.stl`: `trimesh.load(path, force="mesh")`.
- Watertightness: `mesh.merge_vertices()`, `trimesh.repair.fix_normals`, `fill_holes` once. If still
  not `is_watertight`: refuse, naming the file and `len(mesh.facets_boundary)` open loops. Never mesh
  a non-watertight input.

### 2.2 Units

Largest bounding-box extent `e`: `e < 1.0` → metres (scale by 1000); `1.0 <= e < 2000` → mm;
otherwise refuse. `--units in` scales by 25.4. Record `units_in`. A 60 mm sink exported in metres is
the common failure, and this catches it; inches are only by flag.

### 2.3 Orientation (`orient="auto"`)

1. Base bottom: `mesh.facets` groups coplanar triangles; take the facet with the largest area and its
   normal `n`. Rotate so `n` → (0, 0, -1). Tie-break (two equal faces, e.g. a plain block): prefer the
   one whose opposite side has more triangles (fins are on top).
2. Flow direction about z: the fins should run along x. For every triangle above the base
   (determined after step 2.5; iterate once), sum `|n_x| * A` and `|n_y| * A`. Rotate 90° about z if
   `sum|n_x|A > sum|n_y|A`, so the smaller projected blockage faces the inlet. Plate fins along x
   present edges to the flow (small `|n_x|` area); pins are symmetric and either choice is fine.
3. Translate so the base occupies x in [0, L], y in [0, W], z from 0.
4. `orient="+z:-y,+x:+z"`-style overrides are over-engineered; implement `--orient` as a sequence of
   axis rotations applied before auto-detection is skipped, e.g. `--orient "x90 z-90"` (degrees about
   x then z), and `--orient none` to take the file as is (only translation applied). Document the
   convention once in `docs/cad_input.md`.

### 2.4 Base thickness and fin height

Section the mesh at z = 0.25, 0.50, 0.75, ... mm (`trimesh.intersections.mesh_plane` → polygons via
`trimesh.path`). `A0` = area at 0.25 mm. `base_t` = first z where the section area < 0.6 * A0.
`h = z_max - base_t`. If the area never drops: refuse with "no fins found above the base". Validate
against the parametric generator: d3 pd2.2 h35 staggered must give base_t = 4.0 ± 0.3 and h = 35 ± 0.3.

### 2.5 Measurements

- `footprint`: the section polygon(s) at z = base_t / 2; `L`, `W` from its bounds.
- `fin_sections`: polygons at z = base_t + h / 2.
- `min_feature_mm`: for each fin polygon, thickness = short side of `minimum_rotated_rectangle`
  (good enough for pins and plates; note the approximation in the docstring); gap = min pairwise
  `polygon.distance` between fin polygons (use an STRtree, there can be 256 pins). Feature = min of
  the two. For the parametric centre design this must come out as 3.0 mm (pin diameter; the gap is
  3.6 mm).
- `volume_mm3 = mesh.volume`; `fin_volume_mm3` = volume of the part above z = base_t (slice with
  `trimesh.intersections.slice_mesh_plane(cap=True)`); `wetted_area_mm2` = area of the triangles
  above base_t.
- Mass uses the material density (section 4).

### 2.6 Embedding for snappyHexMesh (the delicate part)

Reconstruct what `make_heatsink_for_snappy` does, on an arbitrary mesh, with boolean unions
(`trimesh.boolean.union([...], engine="manifold")`):

1. **Below the floor and beyond the side walls.** Extrude the footprint polygon buffered by +1 mm
   (`shapely buffer(1.0, join_style=2)`) and clipped to x in [0, L] (no extension through inlet or
   outlet planes, which are far away anyway) from z = -1 to z = base_t / 2. Union with the sink.
2. **Above the shroud.** Take the triangles with z ≈ z_max (within 0.05 mm) and normal +z; project to
   polygons (`shapely unary_union` of the triangles); extrude each from z_max - 0.5 to z_max + 1.
   Union. If no such triangles exist (rounded or pointed fin tips), skip the extension and set the
   shroud at z_max + 0.3 mm with a warning "fin tips are not flat; a 0.3 mm tip gap was left" (this is
   the one place the physics differs from the study and it must be in the report).
3. Scale to metres and write `snappy_stl`. Check `is_watertight` again; refuse if not.

Regression for this step: run the parametric centre design's *clean* `heatsink.stl` through
`load()` and mesh it with the esi flavour; fluid and solid cell counts must be within 3 % of meshing
the parametric `heatsink_snappy.stl` the same way (`work/cases/test_esi_coarse` has the reference
counts; re-run it if in doubt). Add this as a slow test (`@pytest.mark.slow`, ~5 minutes).

### 2.7 `inspect_figure`

matplotlib top view in mm: footprint outline, fin sections filled, the chip rectangle dashed (when
given), an arrow for the flow, and the measured numbers in the title. This is the first thing a user
checks, so it must be right before any meshing happens.

## 3. Generalise `src/make_case.py`

Introduce a domain description and make the existing templates read from it. The parametric path
must produce byte-identical dictionaries to today's (golden-file test, step 7).

```python
@dataclass
class DomainSpec:
    L: float; W: float; base_t: float; h: float          # m
    chip_x0: float; chip_x1: float; chip_y0: float; chip_y1: float   # m, absolute in the duct frame
    power_W: float; T_in_K: float = 298.15
    kappa_solid: float = 200.0; rho_solid: float = 2700.0
    x_in: float = None; x_out: float = None             # default -1.0*L and L + 2.0*L (today's -0.06 / 0.18)
    base_cell: float = 0.003
    tip_gap: float = 0.0                                # > 0 only when the importer could not extend the tips
```

- `block_mesh_dict(dom)`: `X = [x_in, chip_x0, chip_x1, x_out]`, `Y = [0, chip_y0, chip_y1, W]`,
  `NX[i] = max(1, round((X[i+1]-X[i]) / base_cell))` (gives today's 25/10/45 and 5/10/5 exactly;
  assert that in the test), `nz = max(4, round(H / base_cell))`, `H = base_t + h + tip_gap`.
- `snappy_dict(dom, ...)`: refinementBox x from `-0.2 L` to `L + max(0.025, 0.4 L)` (today's -0.012 .. 0.085 exactly), y `-0.001 .. W + 0.001`;
  pinBox x `-0.003 .. L + 0.006`, z from `base_t - 0.001`; fluid inside point
  `(x_in / 2 - 0.0005, W / 2 + 0.0005, H / 2 + 0.0004)`; solid inside point
  `(L / 2 + 0.0005, W / 2 + 0.0005, base_t / 2 + 0.0001)`. For an imported model, verify the solid
  point with `trimesh.contains` and, if it is outside (a sink with a central hole), search a 5 x 5
  grid over the footprint for the first point inside the base slab.
- Hydraulic diameter: `A = W * H`, `Dh = 4 A / (2 (W + H))`. Chip flux: `power / ((chip_x1-chip_x0) * (chip_y1-chip_y0))`.
- `solid_T`: `grad = q_flux / kappa_solid`. `AL_PROPS` becomes a template with `kappa` and `rho`
  (keep `Cv` as is); `KAPPA_AL` stays as the default.
- `write_case_from_model(model: SinkModel, dom: DomainSpec, V, mesh, out, n_proc, n_iter, flavour, n_layers)`
  copies `model.snappy_stl` to `constant/geometry/heatsink.stl` and writes everything else as today.
  `case.json` gets `"kind": "cad"`, the measurements, and `"analytic": {}`.
- `write_case(spec, ...)` (parametric) builds its `DomainSpec` from the spec and the old constants and
  calls the same internals, still exporting its own CadQuery `heatsink_snappy.stl` (do not route the
  parametric path through the importer; the study must stay reproducible).
- Refinement level for CAD input: `coarse_level = clamp(ceil(log2(base_cell / (min_feature / 2.5))), 2, 4)`
  (3 mm / (2 mm / 2.5) → level 2 for the 2 mm pins, level 3 for a 1.5 mm plate), medium = +1,
  fine = +2, box levels as today. Warn when the level is 4 ("fine features; expect a large mesh").
  Expose `--surf-level` to override.

## 4. Materials and chip input

`--material aluminium|copper` → (kappa, rho): aluminium (200, 2700), copper (385, 8960). Fin mass =
`fin_volume_mm3 * rho * 1e-6` g. The parametric path keeps aluminium.

`--chip 30x30` (x by y, mm) or `--chip 30`; `--chip-offset dx,dy` mm from the base centre;
`--power W`. Refuse if the chip rectangle leaves the footprint bounds. Put the chip rectangle on the
inspect figure.

## 5. CLI `src/run.py`

```
--cad FILE | --cad-dir DIR | --inspect FILE
--chip, --chip-offset, --power, --material, --V (repeatable), --mesh, --np, --iters, --layers
--orient, --units, --surf-level, --base-cell
--out DIR            default results/cad/<stem>
--dry-run            import, measure, write the case, no meshing (what the cloud can do)
--mesh-timeout, --solve-timeout (same defaults as studies.custom)
--flavour org|esi    esi = mesh only, cloud testing
```

Behaviour:
- Per file: `out/<stem>_V{V:g}_{mesh}/` case; run via the same `run()` / `already_done()` helpers as
  `studies.run_one` (move those two helpers into a small `src/runner.py` used by `sweep.py`,
  `studies.py` and `run.py`; no behaviour change). `results.json` as today plus the `SinkModel`
  fields under `"model"`.
- `--cad-dir`: every `.step/.stp/.stl` in the folder, one at a time (D12), resumable; then
  `sweep.csv` with the sweep columns (`sweep.flatten` with `d/pd/h/layout` empty and `n_pins`,
  `fin_mass_g`, `analytic_*` from the model or blank), `pareto.csv` and `pareto.png` via
  `analysis.pareto_front` / `fig_pareto` (title from `--title`), and a short `results.md`: table,
  the sentence "No hand calculation exists for these shapes; values are CFD only, coarse mesh," and
  every model warning.
- `--inspect`: print the measurements as a table and write `<stem>_inspect.png`.
- Exit codes: 0 ok, 2 input refused (message says why and what to do), 3 meshing failed (point to
  the log), 4 solver failed/timeout.

## 6. Documentation

- `docs/cad_input.md`: the conventions (orientation, units, chip placement, what the tool measures,
  the embedding), how to run, what is and is not validated (no hand calc, no surrogate, tip-gap
  warning, mesh level from feature size, the study's own limitations still apply), exit codes.
- README: a "Run your own CAD" section (6 lines) pointing to the doc.
- `PROGRESS.md`: add `T12 CAD input` with the acceptance line from section 8 and mark it when done.
- `DECISIONS.md`: D13 (parametric path not routed through the importer, and why), D14 (tip-gap
  fallback), D15 (feature-size refinement rule).

## 7. Tests (pytest; fast ones run in `make test`)

Fast (no mesher):
1. `test_make_case_golden`: generate the centre design and one plate-fin case with the refactored
   code into a temp dir; every file under `system/` and `0/` must equal the golden copies in
   `tests/golden/` **generated from master before the refactor** (do this first: check out master,
   run `python -m src.make_case --d 3 --pd 2.2 --h 35 --layout staggered --V 4 --mesh coarse --out tests/golden/centre`
   and the plate case, strip nothing, commit them on the branch).
2. `test_blocking_counts`: `NX == [25,10,45]`, `NY == [5,10,5]` for the study's domain.
3. `test_import_parametric_roundtrip`: export the centre design's clean STL and STEP with
   `geometry.export_all`, `load()` both: L = W = 60 ± 0.1, base_t = 4 ± 0.3, h = 35 ± 0.3,
   min_feature = 3.0 ± 0.1, n_fins = 77, volume within 0.5 % of `cad_volume_mm3`, warnings empty.
4. `test_orientation`: rotate the centre design STL by x90 and by z90 before loading; the model
   must come back identical (L, W, base_t, h, n_fins) and the transform recorded.
5. `test_plate_orientation`: a plate-fin STL rotated z90 must come back with plates along x
   (check `sum|n_x|A < sum|n_y|A` on the loaded model, or simply that `W` is 60 and the fin
   polygons are long in x).
6. `test_units`: the same STL scaled to metres loads to the same measurements with `units_in == "m"`.
7. `test_refusals`: a cube with one face removed (non-watertight) → refusal mentioning open loops;
   a plain block (no fins) → "no fins found"; a chip larger than the base → refusal; a STEP with two
   solids → refusal.
8. `test_cli_dry_run`: `python -m src.run --cad <plate.step> --chip 30x30 --power 100 --dry-run --out tmp`
   writes the case, `case.json["kind"] == "cad"`, q_flux = 100 / 0.0009.

Slow (`-m slow`, needs the esi mesher; run in the cloud before handing to the laptop):
9. `test_mesh_counts_imported_vs_parametric`: section 2.6 regression (3 %).
10. `test_mesh_plate_step`: a plate-fin STEP from `geometry.export_platefin` meshes at coarse with
    both regions "Mesh OK" in `log.checkMesh.*`.

## 8. Laptop acceptance (OpenFOAM 14; this is the real check)

One job (section 9) that runs, at coarse / 4 m/s / 600 iterations / np 8:
- `results/cad/centre_from_step/` from `work/geom/d3_pd2.2_h35_staggered/heatsink.step`
- `results/cad/plate_from_step/` from the plate-fin STEP used in the study (`PlateFinSpec(1.5, 9, 35)`)

PASS: R within 2 % and dP within 5 % of the study's own runs of the same designs on the same mesh
(`results/sweep.csv` row `d3_pd2.2_h35_staggered_V4_coarse`: R 0.3872, dP 143.0;
`results/plate_comparison.json`: R 0.3790, dP 28.9). Record both in `docs/cad_input.md`. If dP
misses by more than 5 %, the embedding or the refinement rule differs from the study: compare cell
counts first, then the snappy dictionaries (diff against the parametric case).

Then one genuinely foreign file as a demo: ask Griffin for any heat sink STEP he has (or make a
simple folded-fin or hexagonal-pin sink in CadQuery and export it), run it, and put the inspect
figure and the render in the README section.

## 9. How the laptop side works (unchanged conventions)

- Laptop repo: `C:\Users\Griff\Projects\heatsink-cfd` (WSL path `/mnt/c/Users/Griff/Projects/heatsink-cfd`),
  on master. Pushes from the cloud go file by file via `device_commit_files` (force) from
  `/mnt/user-data/outputs`; verify with `tr -d '\r' < f | md5sum` on the laptop, stale pushes happen,
  retry. The laptop has `Makefile.txt`, not `Makefile`.
- Jobs: `scripts/mkjob.sh <body> <name>` writes `jobs/<name>.sh` with an md5 gate on `src/*.py`;
  push the job to `C:\Users\Griff\Projects\cfd-sims\jobs\`; `runner.sh` there runs jobs in order;
  logs in `cfd-sims/logs/<job>.log`, status in `runner-status.txt`. Regenerate jobs after any `src`
  change (the gate aborts otherwise).
- Solve on the laptop only; mesh tests in the cloud with `--flavour esi`.
- Commits end with the two attribution lines the session uses (see the previous commits on master).

## 10. Order of work and checkpoints

1. Golden files from master (step 7.1). Commit.
2. `cad_import.py` loading, units, orientation, measurements, `--inspect`. Tests 3-7. Commit.
3. Embedding (2.6) and the slow test 9 in the cloud. Commit. Report the cell counts.
4. `make_case.py` refactor with `DomainSpec`; golden test 1 and test 2 green. Commit.
5. `src/runner.py` extraction (no behaviour change; `make quick` still passes on the laptop later).
6. `src/run.py` CLI, test 8, slow test 10. Commit.
7. Docs (section 6). Commit.
8. Laptop acceptance job (section 8). Record the numbers. Mark T12 in PROGRESS.
9. Foreign-file demo; README section. Commit. Merge `cad-input` into master only after step 8
   passes.

Estimated: steps 1-7 about a day of cloud work; step 8 about 30 minutes of laptop time.

## 11. Out of scope (say so in the docs, do not build)

Surrogate or optimisation over arbitrary CAD; hand calculation for non-array shapes; multi-body
assemblies; tip bypass as a design variable (the fallback gap is a warning, not a feature); heat
spreaders, contact resistance or non-uniform chip flux; mesh independence per geometry (the coarse
level is a starting point, the medium level is one flag away); non-rectangular base plates (the
footprint bounds are used as the duct; a round base will work but the duct will be its bounding box).

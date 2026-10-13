# Mesh independence study

Centre design (d = 3 mm, p/d = 2.2, h = 35 mm, staggered) at 4 m/s, three refinement levels
(background 3 mm cells; pin-surface refinement level 2 / 3 / 4 = 0.75 / 0.375 / 0.19 mm; 4 prism layers on the
fluid side of every level). 6 MPI processes on a 12-core laptop with 19 GB of memory.

| mesh | fluid cells | solid cells | T_chip,max C | R K/W | dP Pa | iterations | meshing | solve | status |
|---|---|---|---|---|---|---|---|---|---|
| coarse | 424,486 | 64,132 | 63.74 | 0.3872 | 143.0 | 1500 | 2.5 min | 13.3 min | converged (T_max drift < 0.03 K between 400 and 1500 iterations) |
| medium | 1,770,572 | 419,592 | 62.27 | 0.3728 | 107.0 | 1236 | 12.5 min | 59.7 min | hit the 60 min cap (residuals p 3.6e-4, U 1.4e-4, h 1.4e-4) |
| fine | 7,591,284 | 2,070,556 | n/a | n/a | n/a | 0 | not recorded | not run | meshing did not finish within the 60 min cap (status `failed`) |

Hand calculation for reference: R = 0.378 K/W, dP = 155 Pa.

Notes on the table: the fine-level cell counts are as recorded in `results/mesh_study.csv`; the meshing never completed, so
treat them as indicative only. The meshing times in that CSV are all 0.0 (not captured), so the 2.5 and 12.5 min meshing times
for coarse and medium come from the run logs on the laptop and cannot be re-checked from the repository. No `checkMesh` logs are
kept in the repository either; the CSVs only record that checkMesh passed (`mesh_ok_fluid`, `mesh_ok_solid`).

## Result

- Coarse to medium: R changes by 3.7 % (0.387 to 0.373), dP by 25 % (143 to 107 Pa).
- Medium to fine: **not measured**. Meshing the fine level (about 9.7 million cells in total) did not finish within the 60 minute
  cap and a single fine solution would need many hours on this laptop, so the PLAN criterion "medium to fine change < 3 %" is
  **not met**. The coarse mesh (0.49 M cells in total, 0.42 M fluid) also exceeds the PLAN's 400k-cell target for T3 (DECISIONS D10).
- For the centre design thermal resistance changes 3.7 % between coarse and medium and sits within 2.6 % (coarse) and 1.3 % (medium) of the hand
  calculation. Pressure drop is *not* mesh-converged: it falls as the mesh is refined and the medium value is 31 % below
  the correlation. Absolute dP values from the sweep are therefore uncertain by something like 25-30 % for dense arrays; this is an observed offset
  between two meshes, not a bound, because dP was still falling with refinement and no finer level exists.

## Consequence for the sweep (DECISIONS.md D11)

The 36-design sweep runs on the coarse mesh, because a medium-mesh case costs about 75 minutes and the sweep would take more than
a day. Rankings and trends (which is what the Pareto study and the surrogate use) are what the sweep is trusted for;
three further designs were re-run on the medium mesh to quantify the coarse-to-medium offset (below).

## Medium-mesh re-runs of three further designs

| design (4 m/s) | R coarse | R medium | change | dP coarse Pa | dP medium Pa | change | dP hand Pa |
|---|---|---|---|---|---|---|---|
| d3.7, pd1.8, h35, inline | 0.340 | 0.336 | -1.2 % | 153 | 116 | -24.2 % | 131 |
| d3, pd2.2, h35, inline | 0.418 | 0.407 | -2.6 % | 85 | 66 | -22.2 % | 64 |
| d4, pd2.8, h35, inline | 0.796 | 0.707 | -11.1 % | 24 | 23 | -4.3 % | 22 |

The offset is **not uniform**. For the two denser arrays the medium mesh gives 22-24 % lower dP and 1-3 % lower R, and the medium dP lands close to the hand calculation (66 vs 64 Pa, 116 vs 131 Pa). For the sparsest array dP barely moves (-4 %) but R drops 11 %, so the coarse mesh over-predicts the resistance of sparse, large-pin designs. The ordering of these three designs is the same on both meshes, but the coarse sweep slightly understates how good sparse designs are and overstates the pressure drop of dense ones, so the Pareto front would shift somewhat on a finer mesh.

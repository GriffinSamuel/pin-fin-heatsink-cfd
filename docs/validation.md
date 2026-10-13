# Validation against hand calculations

Centre design, coarse mesh. Hand calculation: ESDU 73031 (Nu), Gaddis-Gnielinski (dP), pin-fin efficiency, NTU treatment of the array, Lee et al. spreading resistance (see src/analytic.py).

| V m/s | R CFD | R hand | ratio | dP CFD | dP hand | ratio | T_out CFD | T_out hand | Q chip W | Q air W (area-averaged outlet T, over-estimates) |
|---|---|---|---|---|---|---|---|---|---|---|
| 2 | 0.521 | 0.523 | 1.00 | 41 | 35 | 1.19 | 44.5 | 42.9 | 100.0 | 107.4 |
| 4 | 0.387 | 0.378 | 1.03 | 143 | 155 | 0.92 | 34.8 | 34.0 | 100.0 | 108.3 |
| 6 | 0.337 | 0.321 | 1.05 | 303 | 353 | 0.86 | 31.6 | 31.0 | 100.0 | 109.1 |

Largest deviation: R 5 %, dP 19 % -> PASS (within 30 %).

## Discussion

The correlations describe long tube banks with uniform approach flow. Differences to expect: the 4 mm step onto the base plate and the shroud contact at the pin tips are not in the hand calculation; the array has only 5-16 rows (row-correction factors carry their own uncertainty); the CFD uses four prism layers with wall functions on a coarse mesh, and omega on the pin/base interface is zero-gradient (D9); and the correlation uncertainty itself is quoted at about 15-25 %.

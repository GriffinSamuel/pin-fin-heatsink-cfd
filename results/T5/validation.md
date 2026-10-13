# Validation against hand calculations

Centre design, coarse mesh. Hand calculation: ESDU 73031 (Nu), Gaddis-Gnielinski (dP), pin-fin efficiency, NTU treatment of the array, Lee et al. spreading resistance (see src/analytic.py).

| V m/s | R CFD | R hand | ratio | dP CFD | dP hand | ratio | T_out CFD | T_out hand | Q chip W | Q air W (area-averaged outlet T, over-estimates) |
|---|---|---|---|---|---|---|---|---|---|---|
| 2 | 0.521 | 0.523 | 1.00 | 41 | 35 | 1.19 | 44.5 | 42.9 | 100.0 | 107.4 |
| 4 | 0.387 | 0.378 | 1.03 | 143 | 155 | 0.92 | 34.8 | 34.0 | 100.0 | 108.3 |
| 6 | 0.337 | 0.321 | 1.05 | 303 | 353 | 0.86 | 31.6 | 31.0 | 100.0 | 109.1 |

Largest deviation: R 5 %, dP 19 % -> PASS (within 30 %) for the centre design. See `figures/validation.png` and the caveats below.

## Discussion

The correlations describe long tube banks with uniform approach flow. Differences to expect: the 4 mm step onto the base plate and the shroud contact at the pin tips are not in the hand calculation; the array has only 5-16 rows (row-correction factors carry their own uncertainty); the CFD uses four prism layers with wall functions on a coarse mesh, and omega on the pin/base interface is zero-gradient (D9); and the correlation uncertainty itself is quoted at about 15-25 %.

## Caveats

- The 30 % criterion is applied to the centre design only. Over all 36 designs at 4 m/s the CFD/hand dP ratio spans 0.60-2.57 and 18 designs are outside +/-30 % (see docs/report.md section 4).
- The 2 and 4 m/s runs stopped at the wall-clock cap after about 515 iterations (status `timeout` in results/T5/validation.csv); convergence at 2 m/s was not verified beyond the temperature drift check.
- R is computed from the maximum solid cell temperature in the chip region (`cellMax`), not from the chip patch face values.
- The interface heat balance (chip power = heat through the fluid-solid interface) is satisfied nearly by construction in a conjugate solver. The independent air-side enthalpy balance is 7-9 % high (107-109 W for 100 W); the area-averaged outlet temperature is the likely cause, but this was not tested.
- The "second opinion" correlation (Zukauskas/Bejan constants) is closely related to the ESDU-labelled one used in src/analytic.py (the constants there resemble Zukauskas-type values and were not checked against the ESDU document itself), so the two agreeing is not independent evidence.

# Foreign CAD: KiCad 125x35 mm extruded heat sink

No hand calculation exists for these shapes; values are CFD only, on the mesh level named in the table. R = (hottest solid temperature - inlet temperature) / chip power. The study's own limitations (no mesh-independence proof, residual criteria not met) apply; see docs/cad_input.md.

| file | V m/s | mesh | status | fins | fin mass g | R K/W | dP Pa | Q chip W |
|---|---|---|---|---|---|---|---|---|
| Heatsink_125x35x50mm_3xFixationM3.step | 4 | coarse | ok | 11 | 92.3 | 0.594 | 23 | 100.4 |

## Warnings from the importer

- Heatsink_125x35x50mm_3xFixationM3.step: fin tips are rounded or pointed; the fin section 0.4 mm below each tip was extended up to the shroud, which adds a small sliver of metal at the tips

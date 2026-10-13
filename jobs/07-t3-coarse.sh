# T3: coarse CHT case of the centre design, 300 iterations, 6 processes
cd $HOME/heatsink-cfd || exit 1
source /opt/openfoam14/etc/bashrc
RES=/mnt/c/Users/Griff/Projects/heatsink-cfd/results/T3; mkdir -p "$RES"
CASE=work/cases/center_coarse; rm -rf $CASE
.venv/bin/python -m src.make_case --d 3 --pd 2.2 --h 35 --layout staggered --V 4 --mesh coarse --np 6 --iters 300 --out $CASE || exit 1
( cd $CASE && timeout 50m ./Allrun ); echo "Allrun exit $?"
cd $CASE
for f in log.*; do echo "== $f: $(grep -c FATAL $f) FATAL"; done
grep -E "^Snapped mesh|Finished meshing" log.snappyHexMesh
grep -E "cells:|Mesh OK|Failed" log.checkMesh.fluid log.checkMesh.solid 2>/dev/null
tail -30 log.foamMultiRun | head -60
grep -B2 -A8 FATAL log.* | head -60
ls postProcessing 2>/dev/null; find postProcessing -name "*.dat" | head -30
cd $HOME/heatsink-cfd && .venv/bin/python -m src.results $CASE
cp $CASE/results.json $CASE/case.json $CASE/log.* "$RES/" 2>/dev/null
cp -r $CASE/postProcessing "$RES/" 2>/dev/null
echo "T3 job done"

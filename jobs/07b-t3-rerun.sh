# T3 rerun after syncing the latest code (functions header fix), plus a full env check
SRC=/mnt/c/Users/Griff/Projects/heatsink-cfd
cd $HOME/heatsink-cfd || exit 1
for d in src tests scripts jobs; do rm -rf "$d"; cp -r "$SRC/$d" .; done; find src tests scripts jobs -type f -exec sed -i 's/\r$//' {} +
[ -f "$SRC/Makefile.txt" ] && cp "$SRC/Makefile.txt" Makefile; cp "$SRC"/*.md "$SRC"/LICENSE . 2>/dev/null
set +u; bash scripts/env_check.sh 2>&1 | tee docs/env.txt; cp docs/env.txt "$SRC/results/T0/env.txt"
source /opt/openfoam14/etc/bashrc
RES=$SRC/results/T3; mkdir -p "$RES"
CASE=work/cases/center_coarse; rm -rf $CASE
.venv/bin/python -m src.make_case --d 3 --pd 2.2 --h 35 --layout staggered --V 4 --mesh coarse --np 6 --iters 400 --out $CASE || exit 1
head -3 $CASE/system/functions
( cd $CASE && timeout 50m ./Allrun ); echo "Allrun exit $?"
cd $CASE
grep -n "Constructing functionObjects" log.foamMultiRun | head -2
grep -E "cells:|Mesh OK|Failed" log.checkMesh.fluid log.checkMesh.solid 2>/dev/null
tail -12 log.foamMultiRun
grep -B2 -A8 FATAL log.* | head -40
ls postProcessing 2>/dev/null; find postProcessing -name "*.dat" | head -30
cd $HOME/heatsink-cfd && .venv/bin/python -m src.results $CASE
cp $CASE/results.json $CASE/case.json $CASE/log.* "$RES/" 2>/dev/null; rm -rf "$RES/postProcessing"; cp -r $CASE/postProcessing "$RES/" 2>/dev/null
echo "T3 rerun done"

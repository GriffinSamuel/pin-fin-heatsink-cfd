# T3: zeroGradient on the non-coupled remnant patch (as in hotWire tutorial)
SRC=/mnt/c/Users/Griff/Projects/heatsink-cfd
cd $HOME/heatsink-cfd || exit 1
for d in src tests scripts jobs; do rm -rf "$d"; cp -r "$SRC/$d" .; done; find src tests scripts jobs -type f -exec sed -i 's/\r$//' {} +
source /opt/openfoam14/etc/bashrc
RES=$SRC/results/T3; mkdir -p "$RES"
CASE=work/cases/center_coarse; rm -rf $CASE
.venv/bin/python -m src.make_case --d 3 --pd 2.2 --h 35 --layout staggered --V 4 --mesh coarse --np 6 --iters 400 --out $CASE || exit 1
grep -c "heatsink  *{ type zeroGradient" $CASE/0/fluid/omega
( cd $CASE && timeout 50m ./Allrun ); echo "Allrun exit $?"
cd $CASE
grep -a -c "^Time = " log.foamMultiRun; tail -5 log.foamMultiRun | cut -c1-150
grep -a "Solving for omega" log.foamMultiRun | tail -2 | cut -c1-150
cat postProcessing/fluid/yPlus*/0/yPlus.dat | tail -3
cd $HOME/heatsink-cfd && .venv/bin/python -m src.results $CASE; cat $CASE/results.json
cp $CASE/results.json $CASE/case.json $CASE/log.* "$RES/" 2>/dev/null; rm -rf "$RES/postProcessing"; cp -r $CASE/postProcessing "$RES/" 2>/dev/null
echo "T3 spalding done"

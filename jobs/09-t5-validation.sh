# T5: validation at 2/4/6 m/s on the chosen mesh (MESH env or medium), two cases at a time
cd $HOME/heatsink-cfd || exit 1
source /opt/openfoam14/etc/bashrc
SRC=/mnt/c/Users/Griff/Projects/heatsink-cfd
MESH=${MESH:-medium}
.venv/bin/python -m src.studies validate --mesh $MESH --np 6 --jobs 2 --iters 1500 2>&1 | tail -40
mkdir -p "$SRC/results/T5"; cp results/validation.csv docs/validation.md "$SRC/results/T5/" 2>/dev/null
for c in work/validation/*/; do n=$(basename $c); mkdir -p "$SRC/results/T5/$n"; cp $c/results.json $c/case.json $c/log.foamMultiRun "$SRC/results/T5/$n/" 2>/dev/null; done
echo "T5 job done"

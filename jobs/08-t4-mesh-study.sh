# T4: mesh independence study, centre design at 4 m/s, coarse/medium/fine, one case at a time (6 procs)
cd $HOME/heatsink-cfd || exit 1
source /opt/openfoam14/etc/bashrc
SRC=/mnt/c/Users/Griff/Projects/heatsink-cfd
for d in src tests scripts; do rm -rf "$d"; cp -r "$SRC/$d" .; done; find src tests scripts -type f -exec sed -i 's/\r$//' {} +
mkdir -p docs results
.venv/bin/python -m src.studies mesh --np 6 --jobs 1 --iters 1500 2>&1 | tail -40
mkdir -p "$SRC/results/T4"; cp results/mesh_study.csv docs/mesh_study.md "$SRC/results/T4/" 2>/dev/null
for c in work/mesh_study/*/; do n=$(basename $c); mkdir -p "$SRC/results/T4/$n"; cp $c/results.json $c/case.json $c/log.foamMultiRun $c/log.snappyHexMesh $c/log.checkMesh.* "$SRC/results/T4/$n/" 2>/dev/null; done
echo "T4 job done"

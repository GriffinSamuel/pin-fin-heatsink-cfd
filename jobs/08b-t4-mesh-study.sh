# auto-generated; waits for synced sources
SRC=/mnt/c/Users/Griff/Projects/heatsink-cfd
ok=0; for t in $(seq 1 40); do ok=1;
  [ "$(tr -d '\r' < $SRC/src/__init__.py | md5sum | cut -d' ' -f1)" = "d41d8cd98f00b204e9800998ecf8427e" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/analysis.py | md5sum | cut -d' ' -f1)" = "0603b9bc0ef4890b0d815b52828d6f4a" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/analytic.py | md5sum | cut -d' ' -f1)" = "61d8fae19bb44e900cbfdd6d300c5296" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/geometry.py | md5sum | cut -d' ' -f1)" = "6044766d38c4e5c6a376e994d01fd059" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/make_case.py | md5sum | cut -d' ' -f1)" = "af14b03e3ce8663611631fbcfa9f282a" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/results.py | md5sum | cut -d' ' -f1)" = "e19e7cef0ac15f04d5660003653caac3" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/studies.py | md5sum | cut -d' ' -f1)" = "23e557cc818a496cf71b1d4315f83ea6" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/surrogate.py | md5sum | cut -d' ' -f1)" = "694848552c8b5eb23fd4a0b6fcb6ee84" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/sweep.py | md5sum | cut -d' ' -f1)" = "93b8c9b885846f3dbd6ce5d1398c4ef5" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/visuals.py | md5sum | cut -d' ' -f1)" = "e63944ddfe7a64c0745c7bf9826fffc8" ] || ok=0
  [ $ok = 1 ] && break; sleep 5; done
[ $ok = 1 ] || { echo "SOURCES STALE - aborting"; exit 3; }
# T4: mesh independence study, centre design at 4 m/s, coarse/medium/fine, one case at a time (6 procs)
cd $HOME/heatsink-cfd || exit 1
source /opt/openfoam14/etc/bashrc
for d in src tests scripts; do rm -rf "$d"; cp -r "$SRC/$d" .; done; find src tests scripts -type f -exec sed -i 's/\r$//' {} +
mkdir -p docs results
.venv/bin/python -m src.studies mesh --np 6 --jobs 1 --iters 1500 2>&1 | tail -40
mkdir -p "$SRC/results/T4"; cp results/mesh_study.csv docs/mesh_study.md "$SRC/results/T4/" 2>/dev/null
for c in work/mesh_study/*/; do n=$(basename $c); mkdir -p "$SRC/results/T4/$n"; cp $c/results.json $c/case.json $c/log.foamMultiRun $c/log.snappyHexMesh.* $c/log.checkMesh.* "$SRC/results/T4/$n/" 2>/dev/null; done
echo "T4 job done"

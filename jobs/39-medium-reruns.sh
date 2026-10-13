# auto-generated; waits for synced sources
SRC=/mnt/c/Users/Griff/Projects/heatsink-cfd
ok=0; for t in $(seq 1 40); do ok=1;
  [ "$(tr -d '\r' < $SRC/src/__init__.py | md5sum | cut -d' ' -f1)" = "d41d8cd98f00b204e9800998ecf8427e" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/analysis.py | md5sum | cut -d' ' -f1)" = "5d80b945d9129fe48fd575e0b0fa50d6" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/analytic.py | md5sum | cut -d' ' -f1)" = "61d8fae19bb44e900cbfdd6d300c5296" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/geometry.py | md5sum | cut -d' ' -f1)" = "6044766d38c4e5c6a376e994d01fd059" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/make_case.py | md5sum | cut -d' ' -f1)" = "af14b03e3ce8663611631fbcfa9f282a" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/results.py | md5sum | cut -d' ' -f1)" = "e19e7cef0ac15f04d5660003653caac3" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/studies.py | md5sum | cut -d' ' -f1)" = "7afd38c2125d51450abb494ce980afa0" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/surrogate.py | md5sum | cut -d' ' -f1)" = "b8f5f70bdf7bf871e7a8d65b1b981ac9" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/sweep.py | md5sum | cut -d' ' -f1)" = "93b8c9b885846f3dbd6ce5d1398c4ef5" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/visuals.py | md5sum | cut -d' ' -f1)" = "e63944ddfe7a64c0745c7bf9826fffc8" ] || ok=0
  [ $ok = 1 ] && break; sleep 5; done
[ $ok = 1 ] || { echo "SOURCES STALE - aborting"; exit 3; }
# Medium-mesh reruns of 3 designs (coarse->medium offset for R and dP); one at a time, np 8
cd $HOME/heatsink-cfd || exit 1
source /opt/openfoam14/etc/bashrc
for d in src tests scripts; do rm -rf "$d"; cp -r "$SRC/$d" .; done; find src tests scripts -type f -exec sed -i 's/\r$//' {} +
mkdir -p "$SRC/results/T10med"
for spec in "3.7 1.8 35 inline" "3 2.2 35 inline" "4 2.8 35 inline"; do
  set -- $spec
  echo "== medium $spec  $(date +%T)"
  .venv/bin/python -m src.studies custom --d $1 --pd $2 --h $3 --layout $4 --V 4 --mesh medium --np 8 --iters 600 --mesh-timeout 2400 --solve-timeout 3600 --root work/medium 2>&1 | tail -14
  cp results/custom_*_medium.json "$SRC/results/T10med/" 2>/dev/null
done
echo "medium job done"

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
# T9: headless renders of the best, worst and surrogate-optimum cases (coarse, 4 m/s)
cd $HOME/heatsink-cfd || exit 1
source /opt/openfoam14/etc/bashrc
for d in src tests scripts; do rm -rf "$d"; cp -r "$SRC/$d" .; done; find src tests scripts -type f -exec sed -i 's/\r$//' {} +
mkdir -p figures
.venv/bin/pip install -q pyvista matplotlib 2>&1 | tail -1
which xvfb-run || echo "NO xvfb-run"
for c in work/sweep/d2_pd1.8_h35_staggered_V4_coarse work/sweep/d4_pd2.8_h20_inline_V4_coarse $(ls -d work/custom/*d3.7_pd1.8_h35_inline* 2>/dev/null | head -1); do
  echo "== render $c"; ls $c | head -20
  xvfb-run -a .venv/bin/python -m src.visuals --case $c --out figures 2>&1 | grep -v includeEtc | tail -12
done
mkdir -p "$SRC/results/T9"; cp -r figures "$SRC/results/T9/" 2>/dev/null; ls figures
echo "T9 job done"

# auto-generated; waits for synced sources
SRC=/mnt/c/Users/Griff/Projects/heatsink-cfd
ok=0; for t in $(seq 1 40); do ok=1;
  [ "$(tr -d '\r' < $SRC/src/__init__.py | md5sum | cut -d' ' -f1)" = "d41d8cd98f00b204e9800998ecf8427e" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/analysis.py | md5sum | cut -d' ' -f1)" = "73b9cb1b9e64976055c69872236c5699" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/analytic.py | md5sum | cut -d' ' -f1)" = "61d8fae19bb44e900cbfdd6d300c5296" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/geometry.py | md5sum | cut -d' ' -f1)" = "6044766d38c4e5c6a376e994d01fd059" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/make_case.py | md5sum | cut -d' ' -f1)" = "af14b03e3ce8663611631fbcfa9f282a" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/results.py | md5sum | cut -d' ' -f1)" = "e19e7cef0ac15f04d5660003653caac3" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/studies.py | md5sum | cut -d' ' -f1)" = "7afd38c2125d51450abb494ce980afa0" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/surrogate.py | md5sum | cut -d' ' -f1)" = "b8f5f70bdf7bf871e7a8d65b1b981ac9" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/sweep.py | md5sum | cut -d' ' -f1)" = "93b8c9b885846f3dbd6ce5d1398c4ef5" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/visuals.py | md5sum | cut -d' ' -f1)" = "847d57eb72157e57ec3a6427fcd3c9d7" ] || ok=0
  [ $ok = 1 ] && break; sleep 5; done
[ $ok = 1 ] || { echo "SOURCES STALE - aborting"; exit 3; }
cd $HOME/heatsink-cfd || exit 1
for d in src; do rm -rf "$d"; cp -r "$SRC/$d" .; done; find src -type f -exec sed -i 's/\r$//' {} +
C=work/sweep/d4_pd2.8_h20_inline_V4_coarse
ls $C; for t in $(ls -d $C/[0-9]* | tail -2); do echo "== $t"; ls $t; ls $t/solid 2>/dev/null; ls $t/fluid 2>/dev/null; done
.venv/bin/python - <<'PY'
import src.visuals as v
r,t=v.load_case("work/sweep/d4_pd2.8_h20_inline_V4_coarse")
print("times",t[-3:])
for k,b in r.items():
    m=b["internalMesh"]
    print(k,"point:",list(m.point_data.keys()),"cell:",list(m.cell_data.keys()))
PY
mkdir -p figures
for c in work/sweep/d2_pd1.8_h35_staggered_V4_coarse work/sweep/d4_pd2.8_h20_inline_V4_coarse $(ls -d work/custom/*d3.7_pd1.8_h35_inline* | head -1); do
  echo "== render $c"; xvfb-run -a .venv/bin/python -m src.visuals --case $c --out figures 2>&1 | grep -v includeEtc | tail -10
done
mkdir -p "$SRC/results/T9b"; cp -r figures "$SRC/results/T9b/"; ls -la figures | head -40
echo "visuals job done"

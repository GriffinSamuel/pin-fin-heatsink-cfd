# auto-generated; waits for synced sources
SRC=/mnt/c/Users/Griff/Projects/heatsink-cfd
ok=0; for t in $(seq 1 40); do ok=1;
  [ "$(tr -d '\r' < $SRC/src/__init__.py | md5sum | cut -d' ' -f1)" = "d41d8cd98f00b204e9800998ecf8427e" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/analysis.py | md5sum | cut -d' ' -f1)" = "73b9cb1b9e64976055c69872236c5699" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/analytic.py | md5sum | cut -d' ' -f1)" = "61d8fae19bb44e900cbfdd6d300c5296" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/cad_import.py | md5sum | cut -d' ' -f1)" = "41e86c2f69955fce5b427e7f0393268f" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/geometry.py | md5sum | cut -d' ' -f1)" = "6044766d38c4e5c6a376e994d01fd059" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/make_case.py | md5sum | cut -d' ' -f1)" = "eefead6e646faa3c18ad81febdbd075d" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/results.py | md5sum | cut -d' ' -f1)" = "b747e3ac2d8b755bb5a67a12880fb3a1" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/run.py | md5sum | cut -d' ' -f1)" = "063964a784258f0a7c3fca6eb2d329d0" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/runner.py | md5sum | cut -d' ' -f1)" = "e35ba32f7f27ff5059c9257f94d828ca" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/studies.py | md5sum | cut -d' ' -f1)" = "8769a9bed8e63ed16c986fd6ae1b851a" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/surrogate.py | md5sum | cut -d' ' -f1)" = "748213b46294c8b68d7f537be2488d09" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/sweep.py | md5sum | cut -d' ' -f1)" = "9e0aad9bc749bda1e1f60ae7b0ccc401" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/visuals.py | md5sum | cut -d' ' -f1)" = "df0f42945d98d0bbfcad26579706bc82" ] || ok=0
  [ $ok = 1 ] && break; sleep 5; done
[ $ok = 1 ] || { echo "SOURCES STALE - aborting"; exit 3; }
source /opt/openfoam14/etc/bashrc
cd $HOME/heatsink-cfd || exit 1
for d in src; do rm -rf "$d"; cp -r "$SRC/$d" .; done
find src -type f -exec sed -i 's/\r$//' {} +
mkdir -p work/foreign && cp "$SRC/work/foreign/Heatsink_125x35x50mm_3xFixationM3.step" work/foreign/
rm -rf results/cad/foreign_kicad
.venv/bin/python -m src.run --cad work/foreign/Heatsink_125x35x50mm_3xFixationM3.step --chip 30x30 --power 100 --V 4 --mesh coarse --np 8 --iters 600 --out results/cad/foreign_kicad --title "Foreign CAD: KiCad 125x35 mm extruded heat sink" 2>&1 | tail -20
cat results/cad/foreign_kicad/results.md 2>/dev/null | head -20
mkdir -p "$SRC/results/cad"; rm -rf "$SRC/results/cad/foreign_kicad"; cp -r results/cad/foreign_kicad "$SRC/results/cad/" 2>/dev/null
echo "foreign job done"

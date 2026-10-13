# auto-generated; waits for synced sources
SRC=/mnt/c/Users/Griff/Projects/heatsink-cfd
ok=0; for t in $(seq 1 40); do ok=1;
  [ "$(tr -d '\r' < $SRC/src/__init__.py | md5sum | cut -d' ' -f1)" = "d41d8cd98f00b204e9800998ecf8427e" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/analysis.py | md5sum | cut -d' ' -f1)" = "5d80b945d9129fe48fd575e0b0fa50d6" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/analytic.py | md5sum | cut -d' ' -f1)" = "61d8fae19bb44e900cbfdd6d300c5296" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/geometry.py | md5sum | cut -d' ' -f1)" = "6044766d38c4e5c6a376e994d01fd059" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/make_case.py | md5sum | cut -d' ' -f1)" = "af14b03e3ce8663611631fbcfa9f282a" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/results.py | md5sum | cut -d' ' -f1)" = "e19e7cef0ac15f04d5660003653caac3" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/studies.py | md5sum | cut -d' ' -f1)" = "66638a523f9840519c6b74e884aced70" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/surrogate.py | md5sum | cut -d' ' -f1)" = "b98cd5ef6eec7ec6d2ebfdab521ac454" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/sweep.py | md5sum | cut -d' ' -f1)" = "93b8c9b885846f3dbd6ce5d1398c4ef5" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/visuals.py | md5sum | cut -d' ' -f1)" = "e63944ddfe7a64c0745c7bf9826fffc8" ] || ok=0
  [ $ok = 1 ] && break; sleep 5; done
[ $ok = 1 ] || { echo "SOURCES STALE - aborting"; exit 3; }
# T8: surrogate on GPU, then CFD verification of its predicted optimum
cd $HOME/heatsink-cfd || exit 1
source /opt/openfoam14/etc/bashrc
for d in src tests scripts; do rm -rf "$d"; cp -r "$SRC/$d" .; done; find src tests scripts -type f -exec sed -i 's/\r$//' {} +
mkdir -p docs results figures
cp "$SRC/results/T6/sweep.csv" results/sweep.csv
.venv/bin/python -c "import torch;print('torch',torch.__version__,torch.cuda.is_available())" 2>&1 | tail -1 || true
.venv/bin/python -c "import torch,sys;sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null || { echo "installing torch"; .venv/bin/pip install torch 2>&1 | tail -2; .venv/bin/python -c "import torch;print('torch',torch.__version__,torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')" 2>&1 | tail -1; }
.venv/bin/python -m src.surrogate --csv results/sweep.csv --out results --docs docs 2>&1 | grep -v '^ *[0-9.e+-]*,\?$' | tail -45
OPT=$(.venv/bin/python -c "
import json; o=json.load(open('results/surrogate.json'))['optimum']; print(o['d'],o['pd'],o['h'],o['layout'])")
echo "predicted optimum (d pd h layout): $OPT"
set -- $OPT
.venv/bin/python -m src.studies custom --d $1 --pd $2 --h $3 --layout $4 --V 4 --mesh coarse --np 8 --iters 600 2>&1 | tail -15
mkdir -p "$SRC/results/T8"; cp results/surrogate.json results/surrogate_cv.csv results/custom_*.json "$SRC/results/T8/" 2>/dev/null
echo "T8 job done"

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
# After the sweep: analysis, extra velocities for the 10 best designs, equal-mass plate-fin case
cd $HOME/heatsink-cfd || exit 1
source /opt/openfoam14/etc/bashrc
for t in $(seq 1 90); do pgrep -f "src.sweep" >/dev/null || break; sleep 60; done
pgrep -f "src.sweep" >/dev/null && { echo "sweep still running after 90 min"; exit 4; }
for d in src tests scripts; do rm -rf "$d"; cp -r "$SRC/$d" .; done; find src tests scripts -type f -exec sed -i 's/\r$//' {} +
mkdir -p docs results figures
tail -5 results/sweep.log
.venv/bin/python -c "
import pandas as pd; d=pd.read_csv('results/sweep.csv'); print(d.status.value_counts().to_dict())"
echo "== T7 analysis (4 m/s)"
.venv/bin/python -m src.analysis --csv results/sweep.csv --out results --fig figures --docs docs 2>&1 | tail -15
NAMES=$(.venv/bin/python - <<'PY'
import pandas as pd
from src.analysis import load, pareto_front
d=load('results/sweep.csv'); d['dname']=d['name'].str.replace('_V4_coarse','',regex=False)
front=list(pareto_front(d)['dname'])
rest=[n for n in d.sort_values('R_max_K_W')['dname'] if n not in front]
print(' '.join((front+rest)[:10]))
PY
)
echo "10 designs for extra velocities: $NAMES"
echo "$NAMES" > results/top10.txt
.venv/bin/python -m src.sweep --mesh coarse --V 2 6 --np 8 --jobs 1 --iters 600 --only $NAMES 2>&1 | tail -25
MASS=$(.venv/bin/python -c "
import pandas as pd
from src.analysis import load
d=load('results/sweep.csv'); b=d.sort_values('R_max_K_W').iloc[0]; print(b['fin_mass_g'], b['h'])")
echo "best design mass,h: $MASS"
set -- $MASS
.venv/bin/python -m src.studies plate --mesh coarse --np 8 --iters 600 --match-mass $1 --h $2 2>&1 | tail -5
mkdir -p "$SRC/results/T6"; cp results/sweep.csv results/sweep.log results/pareto.csv results/plate_comparison.json results/top10.txt "$SRC/results/T6/" 2>/dev/null
cp -r figures docs "$SRC/results/T6/" 2>/dev/null
echo "post-sweep job done"

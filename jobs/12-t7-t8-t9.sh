# T7 analysis + plate comparison, T8 surrogate on the GPU, T9 renders (after the sweep finished)
cd $HOME/heatsink-cfd || exit 1
source /opt/openfoam14/etc/bashrc
SRC=/mnt/c/Users/Griff/Projects/heatsink-cfd
for d in src tests scripts; do rm -rf "$d"; cp -r "$SRC/$d" .; done; find src tests scripts -type f -exec sed -i 's/\r$//' {} +
mkdir -p docs results figures
echo "== T7 analysis"; .venv/bin/python -m src.analysis --csv results/sweep.csv --out results --fig figures --docs docs 2>&1 | tail -15
echo "== T8 surrogate"; .venv/bin/pip install -q torch 2>&1 | tail -1
.venv/bin/python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
.venv/bin/python -m src.surrogate --csv results/sweep.csv --out results --docs docs --dp-budget ${DP_BUDGET:-150} 2>&1 | tail -30
echo "== T9 renders"
BEST=$(.venv/bin/python -c "import pandas as pd; d=pd.read_csv('results/pareto.csv'); print(d.sort_values('R_max_K_W').iloc[0]['name'])")
WORST=$(.venv/bin/python -c "import pandas as pd; d=pd.read_csv('results/sweep.csv'); d=d[d.status=='ok']; print(d.sort_values('R_max_K_W').iloc[-1]['name'])")
for c in $BEST $WORST; do xvfb-run -a .venv/bin/python -m src.visuals --case work/sweep/$c --out figures --name $c 2>&1 | grep -v includeEtc | tail -8; done
mkdir -p "$SRC/results/T789"; cp -r figures docs results/*.csv results/*.json "$SRC/results/T789/" 2>/dev/null
echo "T7-9 job done"

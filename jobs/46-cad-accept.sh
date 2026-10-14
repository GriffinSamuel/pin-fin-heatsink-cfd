# auto-generated; waits for synced sources
SRC=/mnt/c/Users/Griff/Projects/heatsink-cfd
ok=0; for t in $(seq 1 40); do ok=1;
  [ "$(tr -d '\r' < $SRC/src/__init__.py | md5sum | cut -d' ' -f1)" = "d41d8cd98f00b204e9800998ecf8427e" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/analysis.py | md5sum | cut -d' ' -f1)" = "73b9cb1b9e64976055c69872236c5699" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/analytic.py | md5sum | cut -d' ' -f1)" = "61d8fae19bb44e900cbfdd6d300c5296" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/cad_import.py | md5sum | cut -d' ' -f1)" = "ee9e9e10d6792962ccd0cf0b06c06899" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/geometry.py | md5sum | cut -d' ' -f1)" = "6044766d38c4e5c6a376e994d01fd059" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/make_case.py | md5sum | cut -d' ' -f1)" = "eefead6e646faa3c18ad81febdbd075d" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/results.py | md5sum | cut -d' ' -f1)" = "b747e3ac2d8b755bb5a67a12880fb3a1" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/run.py | md5sum | cut -d' ' -f1)" = "4e1e27f2e014c442676fdba789386cf0" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/runner.py | md5sum | cut -d' ' -f1)" = "e35ba32f7f27ff5059c9257f94d828ca" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/studies.py | md5sum | cut -d' ' -f1)" = "8769a9bed8e63ed16c986fd6ae1b851a" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/surrogate.py | md5sum | cut -d' ' -f1)" = "748213b46294c8b68d7f537be2488d09" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/sweep.py | md5sum | cut -d' ' -f1)" = "9e0aad9bc749bda1e1f60ae7b0ccc401" ] || ok=0
  [ "$(tr -d '\r' < $SRC/src/visuals.py | md5sum | cut -d' ' -f1)" = "df0f42945d98d0bbfcad26579706bc82" ] || ok=0
  [ $ok = 1 ] && break; sleep 5; done
[ $ok = 1 ] || { echo "SOURCES STALE - aborting"; exit 3; }
cd $HOME/heatsink-cfd || exit 1
source /opt/openfoam14/etc/bashrc
for d in src tests scripts; do rm -rf "$d"; cp -r "$SRC/$d" .; done; cp "$SRC/requirements.txt" .
find src tests scripts -type f -exec sed -i 's/\r$//' {} +
.venv/bin/pip install -q shapely manifold3d mapbox_earcut rtree networkx trimesh 2>&1 | tail -3
.venv/bin/python -c "import trimesh, shapely, manifold3d, rtree; print('deps ok', trimesh.__version__, shapely.__version__)" || exit 5
rm -rf work/cad_in results/cad/acceptance
mkdir -p work/cad_in/gen_c work/cad_in/gen_p work/cad_in/files
.venv/bin/python - <<'PY'
from src.geometry import HeatSinkSpec, PlateFinSpec, export_all, export_platefin
import shutil
export_all(HeatSinkSpec(3, 2.2, 35, "staggered"), "work/cad_in/gen_c")
export_platefin(PlateFinSpec(1.5, 9, 35), "work/cad_in/gen_p")
shutil.copy("work/cad_in/gen_c/heatsink.step", "work/cad_in/files/centre_design.step")
shutil.copy("work/cad_in/gen_p/heatsink.step", "work/cad_in/files/plate_fin.step")
PY
.venv/bin/python -m src.run --cad-dir work/cad_in/files --chip 30x30 --power 100 --V 4 --mesh coarse --np 8 --iters 600 --out results/cad/acceptance --title "Acceptance: study designs through the CAD path" 2>&1 | tail -40
echo "== comparison"
.venv/bin/python - <<'PY'
import json
ref = {"centre_design": (0.3872, 142.98), "plate_fin": (0.3790, 28.86)}
ok = True
for k, (R0, P0) in ref.items():
    r = json.load(open(f"results/cad/acceptance/{k}_V4_coarse/results.json"))
    R, P = r.get("R_max_K_W"), r.get("dP_Pa")
    if R is None or P is None:
        print(k, "NO RESULT", r.get("status"), r.get("fail_reason")); ok = False; continue
    eR, eP = (R / R0 - 1) * 100, (P / P0 - 1) * 100
    good = abs(eR) <= 2 and abs(eP) <= 5
    ok &= good
    print(f"{k}: R {R:.4f} (study {R0}, {eR:+.2f} %)  dP {P:.2f} (study {P0}, {eP:+.2f} %)  cells {r.get('cells_fluid')}/{r.get('cells_solid')}  Qchip {r.get('Q_chip_W')}  bal {r.get('interface_balance_err_pct')}  -> {'PASS' if good else 'FAIL'}")
print("ACCEPTANCE", "PASS" if ok else "FAIL")
PY
mkdir -p "$SRC/results/cad"; rm -rf "$SRC/results/cad/acceptance"; cp -r results/cad/acceptance "$SRC/results/cad/" 2>/dev/null
for c in results/cad/acceptance/*_V4_coarse; do mkdir -p "$SRC/results/cad/acceptance_logs/$(basename $c)"; cp $c/log.checkMesh.* $c/case.json $c/log.Allmesh "$SRC/results/cad/acceptance_logs/$(basename $c)/" 2>/dev/null; done
echo "cad acceptance job done"

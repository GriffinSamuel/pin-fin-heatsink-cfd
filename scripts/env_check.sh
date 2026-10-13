#!/usr/bin/env bash
# T0 acceptance: prints the environment; exits non-zero if something essential is missing.
set +u
cd "$(dirname "$0")/.."
ok=0
echo "== date: $(date -Is)"; echo "== host: $(hostname)  $(grep PRETTY /etc/os-release)"
echo "== cores: $(nproc)"; free -g | head -2; df -h ~ | tail -1
echo "== OpenFOAM"; if [ -f /opt/openfoam14/etc/bashrc ]; then source /opt/openfoam14/etc/bashrc; echo "version $WM_PROJECT_VERSION at $WM_PROJECT_DIR"; which foamMultiRun snappyHexMesh splitMeshRegions blockMesh checkMesh decomposePar reconstructPar pvpython 2>&1; else echo "OPENFOAM 14 NOT FOUND"; ok=1; fi
echo "== GPU"; nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv 2>&1 | tail -1
echo "== python"; PY=.venv/bin/python; [ -x $PY ] || { echo "no .venv"; ok=1; PY=python3; }
$PY --version
$PY - <<'PYEOF' || ok=1
import importlib, sys
mods = ["cadquery", "numpy", "scipy", "pandas", "matplotlib", "sklearn", "trimesh", "pyvista", "pytest"]
missing = []
for m in mods:
    try:
        mod = importlib.import_module(m); print(f"  {m:12s} {getattr(mod, '__version__', '?')}")
    except Exception as e:
        print(f"  {m:12s} MISSING ({e})"); missing.append(m)
sys.exit(1 if missing else 0)
PYEOF
echo "== xvfb: $(which xvfb-run || echo missing)"
echo "== exit $ok"; exit $ok

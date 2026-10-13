# T0: set up ~/heatsink-cfd on the laptop (WSL): copy repo, Python venv, env check, unit tests
SRC=/mnt/c/Users/Griff/Projects/heatsink-cfd
DST=$HOME/heatsink-cfd
RES=$SRC/results; mkdir -p "$RES/T0"
mkdir -p "$DST"
for d in src tests scripts jobs; do rm -rf "$DST/$d"; cp -r "$SRC/$d" "$DST/"; done
cp "$SRC"/*.md "$SRC"/requirements.txt "$SRC"/.gitignore "$SRC"/LICENSE "$DST/" 2>/dev/null
[ -f "$SRC/Makefile.txt" ] && cp "$SRC/Makefile.txt" "$DST/Makefile"
cd "$DST" && find . -name "*.sh" -exec sed -i 's/\r$//' {} + && find . -name "*.py" -exec sed -i 's/\r$//' {} +
echo "python: $(python3 --version 2>&1)"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv || { echo "VENV FAILED (python3-venv missing?)"; exit 2; }
fi
.venv/bin/pip install -q -U pip wheel
.venv/bin/pip install -q -r requirements.txt 2>&1 | tail -5 || echo "PIP INSTALL HAD ERRORS"
mkdir -p docs
bash scripts/env_check.sh 2>&1 | tee docs/env.txt
echo "== pytest"; .venv/bin/python -m pytest -q tests 2>&1 | tail -8 | tee docs/pytest_T0.txt
cp docs/env.txt docs/pytest_T0.txt "$RES/T0/"

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
# Fresh-copy check of PLAN T10: copy the repository without results/work/.venv, then `make venv && make quick`
source /opt/openfoam14/etc/bashrc
F=$HOME/fresh_check; rm -rf $F; mkdir -p $F
(cd $SRC && tar cf - --exclude=./work --exclude=./.venv --exclude=./results --exclude=./figures --exclude=__pycache__ --exclude=./.git .) | tar xf - -C $F
cd $F && { [ -f Makefile ] || cp Makefile.txt Makefile; } && find . -type f \( -name '*.py' -o -name 'Makefile' -o -name '*.sh' -o -name '*.txt' \) -exec sed -i 's/\r$//' {} +
( time (make venv > venv.log 2>&1 && make quick NP=8 > quick.log 2>&1; echo "make exit=$?") ) 2>&1 | tail -5
tail -40 quick.log | cut -c1-200
mkdir -p "$SRC/results/T10quick"; cp quick.log venv.log "$SRC/results/T10quick/" 2>/dev/null
echo "quick job done"

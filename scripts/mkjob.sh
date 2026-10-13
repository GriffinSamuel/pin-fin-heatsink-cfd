#!/usr/bin/env bash
# usage: scripts/mkjob.sh <body-file> <job-name>   -> writes jobs/<job-name>.sh with a header that
# waits until the laptop copy of src/*.py matches the checksums computed now (guards against stale pushes).
cd /home/claude/heatsink-cfd
body=$1; name=$2
{
echo "# auto-generated; waits for synced sources"
echo 'SRC=/mnt/c/Users/Griff/Projects/heatsink-cfd'
echo 'ok=0; for t in $(seq 1 40); do ok=1;'
for f in src/*.py; do echo "  [ \"\$(tr -d '\\r' < \$SRC/$f | md5sum | cut -d' ' -f1)\" = \"$(md5sum $f | cut -d' ' -f1)\" ] || ok=0"; done
echo '  [ $ok = 1 ] && break; sleep 5; done'
echo '[ $ok = 1 ] || { echo "SOURCES STALE - aborting"; exit 3; }'
cat "$body"
} > jobs/$name.sh

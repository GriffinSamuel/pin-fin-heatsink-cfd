# Mirror the sweep progress to the Windows folder (re-queue any time)
cd $HOME/heatsink-cfd || exit 1
SRC=/mnt/c/Users/Griff/Projects/heatsink-cfd
cp results/sweep.log results/sweep.csv "$SRC/results/" 2>/dev/null
tail -15 results/sweep.log; echo; grep -c '"status": "ok"' work/sweep/*/results.json 2>/dev/null | grep -c ":1" ; ls work/sweep | wc -l
pgrep -af "src.sweep" | head -2

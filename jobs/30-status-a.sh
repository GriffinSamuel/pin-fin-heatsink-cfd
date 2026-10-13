cd $HOME/heatsink-cfd || exit 1
SRC=/mnt/c/Users/Griff/Projects/heatsink-cfd
cp results/sweep.log results/sweep.csv "$SRC/results/" 2>/dev/null
tail -12 results/sweep.log

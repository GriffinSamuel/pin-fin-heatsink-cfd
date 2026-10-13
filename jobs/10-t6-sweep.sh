# T6: launch the 36-case sweep in the background (so the runner stays free); progress in sweep.log
cd $HOME/heatsink-cfd || exit 1
source /opt/openfoam14/etc/bashrc
SRC=/mnt/c/Users/Griff/Projects/heatsink-cfd
MESH=${MESH:-medium}
mkdir -p results "$SRC/results"
nohup .venv/bin/python -m src.sweep --mesh $MESH --V 4 --np 6 --jobs 2 --iters 1500 > results/sweep.log 2>&1 &
echo "sweep started in background, pid $!"
sleep 30; tail -5 results/sweep.log; cp results/sweep.log "$SRC/results/sweep.log"

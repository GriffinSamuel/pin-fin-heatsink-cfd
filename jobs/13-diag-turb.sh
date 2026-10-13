# Diagnose k/omega collapse in T3 case
cd $HOME/heatsink-cfd/work/cases/center_coarse || exit 1
source /opt/openfoam14/etc/bashrc
ls
echo "--- time dirs"; ls -d [0-9]* processor0/[0-9]* 2>/dev/null | head
echo "--- 0/fluid/k"; cat 0/fluid/k | tail -25
echo "--- boundary fluid"; grep -E "^\s+(interface|heatsink|[a-z_]+)$|type|nFaces" constant/fluid/polyMesh/boundary | head -80
T=$(ls -d processor0/[0-9]* 2>/dev/null | sed 's#processor0/##' | sort -g | tail -1); echo "latest proc time: $T"
if [ -n "$T" ]; then
  reconstructPar -region fluid -time $T > /tmp/rec.log 2>&1; tail -3 /tmp/rec.log
  for f in k omega nut T U p; do postProcess -func "minMaxMagnitude($f)" -region fluid -time $T 2>&1 | grep -E "min|max" | head -4; done
fi
echo "--- tutorial hotWire"
HW=$(find /opt/openfoam14/tutorials -type d -name hotWire* | head -3); echo $HW
for d in $HW; do ls $d $d/0* 2>/dev/null | head -30; done
find /opt/openfoam14/tutorials -path "*CHT*" -name omega | head

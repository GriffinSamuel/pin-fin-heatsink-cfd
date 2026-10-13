cd $HOME/heatsink-cfd/work/cases/center_coarse || exit 1
source /opt/openfoam14/etc/bashrc
run_variant () {  # name kType omegaType nutType
  echo "=== variant $1: k=$2 omega=$3 nut=$4"
  rm -rf processor*/[1-9]* [1-9]*
  for f in k omega nut; do
    python3 - "$f" "$2" "$3" "$4" <<'PY'
import sys,re
f,kt,ot,nt=sys.argv[1:5]
t={'k':kt,'omega':ot,'nut':nt}[f]
s=open(f"0/fluid/{f}").read()
s=re.sub(r'\n    interface_on_heatsink[^\n]*','',s)
extra={'zeroGradient':'{ type zeroGradient; }','wf':None}[t] if t=='zeroGradient' else None
if extra:
    s=s.replace('    heatsink ','    interface_on_heatsink '+extra+'\n    heatsink ',1)
open(f"0/fluid/{f}","w").write(s)
PY
  done
  decomposePar -allRegions -force > log.decv 2>&1
  sed -i 's/^endTime .*/endTime 40;/; s/^writeInterval .*/writeInterval 40;/' system/controlDict
  timeout 10m mpirun -np 6 foamMultiRun -parallel > log.var_$1 2>&1; echo "exit $?"
  grep -a "Solving for omega" log.var_$1 | tail -2 | cut -c1-140
  grep -a "Solving for h," log.var_$1 | tail -1 | cut -c1-140
}
grep -n interface_on 0/fluid/omega
run_variant V1 wf zeroGradient wf
run_variant V2 zeroGradient wf wf

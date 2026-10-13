cd $HOME/heatsink-cfd/work/cases/center_coarse || exit 1
source /opt/openfoam14/etc/bashrc
rm -rf processor*/[1-9]* [1-9]* 
sed -i 's/^endTime .*/endTime 20;/; s/^writeInterval .*/writeInterval 2;/; s/^writeFormat .*/writeFormat ascii;/; s/^purgeWrite .*/purgeWrite 0;/' system/controlDict
timeout 15m mpirun -np 6 foamMultiRun -parallel > log.diag 2>&1; echo "exit $?"
reconstructPar -allRegions > log.recdiag 2>&1; tail -2 log.recdiag
python3 - <<'PY'
import re,os
import numpy as np
def load(f):
    s=open(f,errors='ignore').read()
    m=re.search(r'internalField\s+nonuniform\s+List<(\w+)>\s*\n(\d+)\s*\n\(\n(.*?)\n\)\s*;',s,re.S)
    if not m: return None
    a=np.array(m.group(3).replace('(',' ').replace(')',' ').split(),float)
    return a
# cell centres not available; use cell index (blocks of mesh ordering)
times=sorted([d for d in os.listdir('.') if re.fullmatch(r'\d+',d) and d!='0'],key=int)
for t in times:
    om=load(f"{t}/fluid/omega"); k=load(f"{t}/fluid/k"); nut=load(f"{t}/fluid/nut")
    if om is None: continue
    big=np.where(om>1e5)[0]
    print(t,"omega max %.3g  n>1e5 %d  first idx %s  k min %.3g nut max %.3g"%(om.max(),len(big),big[:5],k.min(),nut.max()))
PY

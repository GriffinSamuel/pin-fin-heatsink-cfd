cd $HOME/heatsink-cfd/work/cases/center_coarse || exit 1
source /opt/openfoam14/etc/bashrc
postProcess -func writeCellCentres -region fluid -time 6 > log.cc 2>&1; tail -3 log.cc; ls 6/fluid | head -30
python3 - <<'PY'
import re,numpy as np
def load(f,vec=False):
    s=open(f,errors='ignore').read()
    m=re.search(r'internalField\s+nonuniform\s+List<(\w+)>\s*\n(\d+)\s*\n\(\n(.*?)\n\)\s*;',s,re.S)
    a=np.array(m.group(3).replace('(',' ').replace(')',' ').split(),float)
    return a.reshape(-1,3) if vec else a
om=load("6/fluid/omega"); C=load("6/fluid/C",True)
idx=np.argsort(-om)[:25]
for i in idx: print(i,"omega %.3g"%om[i],"x %.2f y %.2f z %.2f mm"%tuple(C[i]*1000))
# histogram of z for omega>1e8
big=om>1e7; print("n omega>1e7:",big.sum()); 
z=C[big,2]*1000; print("z hist",np.histogram(z,bins=[0,1,2,3.9,4.1,10,20,30,38,38.9,39.1])[0])
PY

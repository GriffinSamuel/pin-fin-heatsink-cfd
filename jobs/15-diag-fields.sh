cd $HOME/heatsink-cfd/work/cases/center_coarse || exit 1
source /opt/openfoam14/etc/bashrc
rm -rf processor*/[1-9]*
sed -i 's/^endTime .*/endTime 40;/; s/^writeInterval .*/writeInterval 40;/; s/^writeFormat .*/writeFormat ascii;/' system/controlDict
timeout 15m mpirun -np 6 foamMultiRun -parallel > log.diag 2>&1; echo "exit $?"
grep -a -c "^Time = " log.diag
reconstructPar -allRegions -latestTime > log.recdiag 2>&1; tail -3 log.recdiag; ls
python3 - <<'PY'
import re,os,glob
import numpy as np
times=[d for d in os.listdir('.') if re.fullmatch(r'\d+(\.\d+)?',d) and d!='0']
t=max(times,key=float); print("time",t)
for reg in ("fluid","solid"):
  for f in sorted(glob.glob(f"{t}/{reg}/*")):
    s=open(f,errors='ignore').read()
    m=re.search(r'internalField\s+nonuniform\s+List<(\w+)>\s*\n(\d+)\s*\n\(\n(.*?)\n\)\s*;',s,re.S)
    if not m: 
        print(reg,os.path.basename(f),"uniform/other"); continue
    n=int(m.group(2)); txt=m.group(3).replace('(',' ').replace(')',' ')
    a=np.array(txt.split(),float)
    if m.group(1)=='vector': a=a.reshape(-1,3); a=np.linalg.norm(a,axis=1)
    print(reg,os.path.basename(f),n,"min %.4g max %.4g mean %.4g nan %d"%(a.min(),a.max(),a.mean(),np.isnan(a).sum()))
PY

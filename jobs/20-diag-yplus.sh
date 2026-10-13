cd $HOME/heatsink-cfd/work/cases/center_coarse || exit 1
source /opt/openfoam14/etc/bashrc; sed -i "s/^writeFormat .*/writeFormat ascii;/" system/controlDict; reconstructPar -allRegions -time 60 > log.rec60 2>&1; tail -2 log.rec60; ls
ls 60/fluid | head -3
python3 - <<'PY'
import re,numpy as np
def patchvals(f,patch):
    s=open(f,errors='ignore').read()
    i=s.index('boundaryField'); b=s[i:]
    j=b.index(patch+'\n') if (patch+'\n') in b else b.index(patch)
    seg=b[j:j+400000]
    m=re.search(r'value\s+nonuniform\s+List<\w+>\s*\n(\d+)\s*\n\(\n(.*?)\n\)\s*;',seg,re.S)
    if not m: return seg[:300]
    return np.array(m.group(2).split(),float)
for fld in ("yPlus","omega","nut","k"):
    for p in ("interface_on_heatsink","top","floor"):
        try:
            a=patchvals(f"60/fluid/{fld}",p)
            if isinstance(a,str): print(fld,p,"?",a[:150].replace("\n"," "))
            else:
                print(fld,p,len(a),"min %.3g p1 %.3g med %.3g p99 %.3g max %.3g"%(a.min(),np.percentile(a,1),np.median(a),np.percentile(a,99),a.max()))
        except Exception as e: print(fld,p,"err",e)
PY

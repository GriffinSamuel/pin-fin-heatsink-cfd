cd $HOME/heatsink-cfd/work/cases/center_coarse || exit 1
source /opt/openfoam14/etc/bashrc
rm -rf processor*/[1-9]* [1-9]*
for f in k omega nut alphat; do
  sed -i 's#^    heatsink        { type zeroGradient; }#    heatsink        { type zeroGradient; }\n    interface_on_heatsink { type zeroGradient; }#' 0/fluid/$f
done
grep -n interface_on 0/fluid/omega
decomposePar -allRegions -force > log.dec2 2>&1; tail -2 log.dec2
sed -i 's/^endTime .*/endTime 60;/; s/^writeInterval .*/writeInterval 60;/; s/^purgeWrite .*/purgeWrite 0;/' system/controlDict
timeout 15m mpirun -np 6 foamMultiRun -parallel > log.diag2 2>&1; echo "exit $?"
grep -a "Solving for omega" log.diag2 | awk 'NR%10==0' | cut -c1-140
grep -a "Solving for k," log.diag2 | tail -2 | cut -c1-140
grep -a "Solving for h," log.diag2 | tail -1 | cut -c1-140

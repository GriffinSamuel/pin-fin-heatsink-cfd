D=/opt/openfoam14/tutorials/multiRegion/CHT/hotWire
for f in k omega nut U T p alphat; do echo "=== $f"; sed -n '/boundaryField/,$p' $D/0/fluid/$f; done
echo "=== solid T"; sed -n '/boundaryField/,$p' $D/0/solid/T
echo "=== fvSolution"; cat $D/system/fluid/fvSolution | sed -n '/solvers/,$p'
cat $D/system/fvSolution 2>/dev/null | sed -n '/PIMPLE/,$p'
echo "=== schemes"; sed -n '/divSchemes/,/}/p' $D/system/fluid/fvSchemes
echo "=== mesh dict"; cat $D/system/createNonConformalCouplesDict 2>/dev/null | tail -30

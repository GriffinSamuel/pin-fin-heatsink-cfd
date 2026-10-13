S=$(find /opt/openfoam14 -name omegaWallFunctionFvPatchScalarField.H | head -1); echo $S
sed -n '/Description/,/SourceFiles/p' $S | head -90
find /opt/openfoam14 -name "nutLowReWallFunction*" | head -2
find /opt/openfoam14 -iname "*kLowRe*" | head

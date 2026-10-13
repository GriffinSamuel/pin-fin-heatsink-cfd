d=/opt/openfoam14/etc/caseDicts/functions/surfaceFieldValue
ls $d | head -30; sed -n '/^type/,$p' $d/patchValue.cfg | head -40; cat $d/patchFlowRate | tail -8

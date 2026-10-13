source /opt/openfoam14/etc/bashrc
f=$(find /opt/openfoam14/etc/caseDicts -name patchAverage | head -1); echo $f; cat $f | sed -n '/^#/,$p' | head -60
g=$(find /opt/openfoam14/etc/caseDicts -name "surfaceFieldValue*" | head -3); echo $g

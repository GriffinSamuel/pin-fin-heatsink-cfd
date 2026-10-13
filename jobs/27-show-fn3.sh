d=/opt/openfoam14/etc/caseDicts/functions/surfaceFieldValue
cat $d/patchValue.cfg | grep -v '^ *//' ; echo ======; cat $d/patchAverage | grep -v '^ *//'

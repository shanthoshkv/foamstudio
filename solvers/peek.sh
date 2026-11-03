cd /home/shanthoshkv/foamstudio/nozzles/iso9300-R4-fine
ls postProcessing/flowRates/
f=$(ls postProcessing/flowRates/*/surfaceFieldValue.dat | tail -1)
awk 'NR>4 && NR%25==0 {print $1, $2}' $f | tail -12

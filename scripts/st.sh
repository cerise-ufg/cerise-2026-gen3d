#!/bin/bash
# status rapido da frente gen3d no Spark
L=~/cerise2026/gen3d/logs
echo "--- fila A1"; cat $L/a1/queue.log 2>/dev/null | tail -8
for f in $L/a1/*.log $L/a3/*.log; do
  [ -f "$f" ] || continue
  [ "$(basename $f)" = queue.log ] && continue
  n=$(grep -c "ok=True" $f); e=$(grep -c "ok=False" $f)
  last=$(grep -E "ok=|aquecimento|carga do modelo|FIM|Error|error" $f | tail -1 | cut -c1-260)
  echo "$(basename $f): ok=$n falhas=$e | $last"
done
echo "--- sistema"; cat /proc/loadavg; free -g | sed -n 2p
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader 2>/dev/null | tr '\n' ' '; echo
sudo docker ps --format '{{.Names}} {{.Status}}' | tr '\n' ';'; echo

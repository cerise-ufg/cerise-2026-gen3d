#!/bin/bash
# (host) depois da fila protegida: roda o A4 respeitando a memoria (>= necessidade + 10 GB "available") e o vLLM.
C=cerise26_gen3d_dev
LOG=~/cerise2026/gen3d/logs/a4_guarded.log
avail() { awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo; }
log() { echo "$(date -u +%FT%TZ) $*" | tee -a $LOG; }
wait_mem() { while [ "$(avail)" -lt "$1" ]; do log "aguardando memoria: available=$(avail)GB precisa=$1GB"; sleep 60; done; }
until grep -q FILA_PROTEGIDA_FIM ~/cerise2026/gen3d/logs/chain_guarded.log 2>/dev/null; do sleep 30; done
log "fila protegida terminou; iniciando A4"
E="sudo docker exec -e GEN3D_TEST_PRESETS=rapido,padrao -e JUNIT_NAME=rapido_padrao $C"
wait_mem 25; log "pytest rapido+padrao (available=$(avail)GB)"; $E bash /workspace/validation/run_a4.sh pytest
E="sudo docker exec -e GEN3D_TEST_PRESETS=alto -e JUNIT_NAME=alto $C"
wait_mem 26; log "pytest alto (available=$(avail)GB)"; $E bash /workspace/validation/run_a4.sh pytest
wait_mem 14; log "viewer + grades + compressao"
for s in viewer grids compress; do sudo docker exec $C bash /workspace/validation/run_a4.sh $s; done
wait_mem 14; log "agregacao final"
sudo docker exec $C bash /workspace/benchmark/final_aggregate.sh > ~/cerise2026/gen3d/logs/final_aggregate.out 2>&1
sudo docker exec -e GEN3D_ROOT=/workspace $C python /workspace/pipeline/write_ready.py > ~/cerise2026/gen3d/logs/write_ready.out 2>&1
log "A4_GUARDED_FIM"

#!/usr/bin/env bash
# Suite de carga da arquitetura nova (A5). Roda sozinha, em sequencia (cada etapa espera a anterior):
#   1 slot: burst, cache, coalescencia, misto (prioridade x FIFO), polling intenso, backpressure
#   2 slots (pesos compartilhados): burst
# No fim restaura a configuracao de producao (1 slot, todos os presets, GEN3D_TRUST_PROXY=0).
set -u
cd "$(dirname "$0")/.."
up() {  # up <slots> <presets> <trust> <max_queue> <prio>
  sudo GEN3D_WORKER_SLOTS="$1" GEN3D_TRUST_PROXY="$3" GEN3D_MAX_QUEUE="$4" GEN3D_PRIORITY_OFFSETS="$5" \
    docker compose -f compose.yaml up -d --force-recreate "${@:6}" 2>&1 | tail -2
}
log() { echo "[suite $(date +%T)] $*"; }
P_DEF="rapido:0,padrao:30,alto:90"; P_FIFO="rapido:0,padrao:0,alto:0"

log "1 slot: subindo API (trust_proxy=1) + worker1"
up 1 x 1 32 "$P_DEF" api
sudo docker start cerise26_gen3d_worker1 >/dev/null 2>&1 || up 1 x 1 32 "$P_DEF" worker1
bash scripts/wait_health.sh 600 || exit 1
bash loadtest/purge.sh; log "q1_burst";      bash loadtest/lt.sh q1_burst burst --levels 1,2,4,8,16 --seq1 3 --probe-rate 10
log "q1_cache";      bash loadtest/lt.sh q1_cache cache --clients 10 --pool-start 0 --probe-rate 10
log "q1_coalesce";   bash loadtest/lt.sh q1_coalesce coalesce --clients 8 --pool-start 40 --probe-rate 10
bash loadtest/purge.sh; log "q1_mixed_prio"; bash loadtest/lt.sh q1_mixed_prio mixed --clients 8 --jobs-per-client 2 --seed 7 --probe-rate 10
log "API em FIFO pura"; up 1 x 1 32 "$P_FIFO" api; sleep 5
bash loadtest/purge.sh; log "q1_mixed_fifo"; bash loadtest/lt.sh q1_mixed_fifo mixed --clients 8 --jobs-per-client 2 --seed 7 --probe-rate 10
log "API com prioridade e fila maxima 8"; up 1 x 1 8 "$P_DEF" api; sleep 5
bash loadtest/purge.sh; log "q1_backpressure"; bash loadtest/lt.sh q1_backpressure burst --levels 16 --seq1 1 --pool-start 16 --probe-rate 10
log "API padrao"; up 1 x 1 32 "$P_DEF" api; sleep 5
bash loadtest/purge.sh; log "q1_probe";      bash loadtest/lt.sh q1_probe burst --levels 8 --seq1 1 --pool-start 24 --probe-rate 100

log "2 slots (presets rapido,padrao): recriando o worker"
sudo GEN3D_WORKER_SLOTS=2 GEN3D_TRUST_PROXY=1 GEN3D_WORKER_PRESETS=rapido,padrao \
  docker compose -f compose.yaml up -d --force-recreate worker1 2>&1 | tail -1
sleep 20; bash scripts/wait_health.sh 600 || exit 1
sudo docker exec cerise26_gen3d_worker1 env | grep -E 'GEN3D_WORKER_(SLOTS|PRESETS)'
bash loadtest/purge.sh; log "q2_burst";      bash loadtest/lt.sh q2_burst burst --levels 1,2,4,8,16 --seq1 3 --probe-rate 10

log "restaurando producao: 1 slot, todos os presets, trust_proxy=0"
sudo GEN3D_WORKER_SLOTS=1 GEN3D_TRUST_PROXY=0 docker compose -f compose.yaml up -d --force-recreate 2>&1 | tail -2
bash scripts/wait_health.sh 600
bash loadtest/purge.sh
log "fim da suite"

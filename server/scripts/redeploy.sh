#!/usr/bin/env bash
# Reconstroi a imagem do servidor com o codigo atual e recria API + worker em configuracao de producao
# (1 slot, todos os presets, GEN3D_TRUST_PROXY=0). Uso: bash scripts/redeploy.sh  (log em results/redeploy.log)
set -u
cd "$(dirname "$0")/.."
log() { echo "[redeploy $(date +%T)] $*"; }
log "memoria antes:"; free -g | head -2
log "build da imagem cerise26_gen3d_server:latest"
nice -n 19 sudo docker build -q -t cerise26_gen3d_server:latest . || { log "ERRO no build"; exit 1; }
log "recriando containers (1 slot, trust_proxy=0)"
sudo GEN3D_WORKER_SLOTS=1 GEN3D_TRUST_PROXY=0 docker compose -f compose.yaml up -d --force-recreate 2>&1 | tail -4
sleep 15
bash scripts/wait_health.sh 600 || { log "ERRO: health nao ficou ok"; sudo docker logs --tail 30 cerise26_gen3d_worker1; exit 1; }
log "conferindo tmpfs do numba"
sudo docker exec cerise26_gen3d_worker1 sh -c 'echo NUMBA_CACHE_DIR=$NUMBA_CACHE_DIR; mount | grep numba_cache; ls /tmp/numba_cache | head -5'
sudo docker exec cerise26_gen3d_api sh -c 'echo NUMBA_CACHE_DIR=$NUMBA_CACHE_DIR; mount | grep numba_cache'
curl -s http://127.0.0.1:8095/api/v1/health; echo
log "memoria depois:"; free -g | head -2
log "fim"

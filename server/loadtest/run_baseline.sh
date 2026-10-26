#!/usr/bin/env bash
# Baseline MEDIDO da arquitetura de 2025: Flask threaded + modelo real sincrono (baseline_2025/server_2025_real.py).
# Uso: bash loadtest/run_baseline.sh <nolock|lock> [niveis]
# Requer o worker do servidor novo PARADO (teto de 24 GB de GPU desta frente).
set -u
cd "$(dirname "$0")/.."
MODE="${1:-lock}"; LEVELS="${2:-1,2,4,8,16}"
SRV=$PWD; RES=$SRV/results/loadtest; mkdir -p "$RES" "$SRV/results/glbs"
NAME=cerise26_gen3d_baseline2025
sudo docker rm -f $NAME >/dev/null 2>&1
sudo docker run -d --name $NAME --gpus all --ipc=host \
  -e BASELINE_MODE="$MODE" -e BASELINE_PRESET=rapido -e HF_MODULES_CACHE=/tmp/hf_modules -e HF_HUB_OFFLINE=1 \
  -v "$HOME/cerise2026/hf_cache:/root/.cache/huggingface:ro" \
  -v "$HOME/cerise2026/gen3d/hy3dgen_models:/opt/gen3d/hy3dgen_models:ro" \
  -v "$SRV/models/u2net:/root/.u2net:ro" -v "$SRV:/opt/gen3d/server" \
  -p 127.0.0.1:8096:8096 cerise26_gen3d_server:latest python baseline_2025/server_2025_real.py >/dev/null
echo "[baseline $MODE] carregando o modelo..."
for i in $(seq 1 120); do
  curl -s --max-time 2 http://127.0.0.1:8096/ | grep -q Flask && break
  sudo docker ps --format '{{.Names}}' | grep -q $NAME || { echo "baseline morreu"; sudo docker logs --tail 30 $NAME; exit 1; }
  sleep 5
done
sudo docker logs $NAME 2>&1 | grep '2025-real'
bash loadtest/gpu_sampler.sh "$RES/gpu_sync_$MODE.csv" $NAME & SP=$!
sudo docker run --rm --name cerise26_gen3d_loadclient --network host -v "$SRV:/opt/gen3d/server" \
  cerise26_gen3d_server:latest python loadtest/loadtest.py burst --mode sync --base http://127.0.0.1:8096 \
  --images /opt/gen3d/server/loadtest/pool --levels "$LEVELS" --seq1 3 --client-timeout 300 --probe-rate 10 \
  --tag "sync_$MODE" --out "/opt/gen3d/server/results/loadtest/sync_$MODE.json" \
  --save-dir "/opt/gen3d/server/results/glbs/sync_$MODE" 2>&1 | grep -v -e '^NOTE' -e NVIDIA -e SHMEM -e 'docker run' \
  | tee "$RES/sync_$MODE.console.txt"
kill $SP 2>/dev/null
sudo docker logs $NAME > "$RES/server_sync_$MODE.log" 2>&1
sudo docker rm -f $NAME >/dev/null
echo "[baseline $MODE] fim"

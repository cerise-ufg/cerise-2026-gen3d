#!/usr/bin/env bash
# Sobe o servidor de geracao 3D no Spark (API + worker de GPU). Uso: bash scripts/start.sh [slots]
#   slots = 1 (padrao) ou 2 (dois jobs simultaneos no mesmo processo, pesos compartilhados)
set -euo pipefail
cd "$(dirname "$0")/.."
SLOTS="${1:-${GEN3D_WORKER_SLOTS:-1}}"
mkdir -p data models/u2net
if ! sudo docker image inspect cerise26_gen3d_server:latest >/dev/null 2>&1; then
  echo "[start] construindo a imagem cerise26_gen3d_server:latest"
  nice -n 19 sudo docker build -t cerise26_gen3d_server:latest .
fi
if [ ! -s models/u2net/u2net.onnx ]; then
  echo "[start] ERRO: falta models/u2net/u2net.onnx (modelo do rembg; ver README)"; exit 1
fi
AVAIL=$(awk '/MemAvailable/ {printf "%d", $2/1048576}' /proc/meminfo)
echo "[start] memoria disponivel no host: ${AVAIL} GB (o worker usa ~16-22 GB e exige folga de 10 GB)"
if [ "$AVAIL" -lt 30 ]; then
  echo "[start] AVISO: pouca memoria; o worker vai esperar a memoria liberar antes de carregar o modelo"
fi
sudo GEN3D_WORKER_SLOTS="$SLOTS" GEN3D_TRUST_PROXY="${GEN3D_TRUST_PROXY:-0}" GEN3D_MAX_QUEUE="${GEN3D_MAX_QUEUE:-32}" \
  GEN3D_CACHE="${GEN3D_CACHE:-1}" GEN3D_PRIORITY_OFFSETS="${GEN3D_PRIORITY_OFFSETS:-rapido:0,padrao:30,alto:90}" \
  docker compose -f compose.yaml up -d
echo "[start] aguardando o worker carregar o modelo (2-4 min)..."
for i in $(seq 1 90); do
  S=$(curl -s --max-time 3 http://127.0.0.1:8095/api/v1/health | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["status"], d["workers"])' 2>/dev/null || echo "sem-resposta 0")
  echo "  [$i] health: $S"
  case "$S" in ok\ *) break;; esac
  sleep 10
done
curl -s http://127.0.0.1:8095/api/v1/health; echo

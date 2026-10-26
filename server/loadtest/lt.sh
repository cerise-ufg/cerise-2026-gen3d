#!/usr/bin/env bash
# Roda um cenario do teste de carga contra a API nova (http://127.0.0.1:8095), com amostragem de GPU do worker.
# Uso: bash loadtest/lt.sh <tag> <cenario> [args extras do loadtest.py]
set -u
cd "$(dirname "$0")/.."
TAG="$1"; SC="$2"; shift 2
SRV=$PWD; RES=$SRV/results/loadtest; mkdir -p "$RES"
bash loadtest/gpu_sampler.sh "$RES/gpu_$TAG.csv" cerise26_gen3d_worker1 & SP=$!
sudo docker run --rm --name "cerise26_gen3d_loadclient" --network host -v "$SRV:/opt/gen3d/server" \
  cerise26_gen3d_server:latest python loadtest/loadtest.py "$SC" --mode queue --base http://127.0.0.1:8095 \
  --images /opt/gen3d/server/loadtest/pool --tag "$TAG" --out "/opt/gen3d/server/results/loadtest/$TAG.json" "$@" \
  2>&1 | grep -v -e '^NOTE' -e NVIDIA -e SHMEM -e 'docker run' | tee "$RES/$TAG.console.txt"
kill $SP 2>/dev/null
curl -s http://127.0.0.1:8095/metrics > "$RES/metrics_$TAG.txt"
sudo docker exec cerise26_gen3d_api python -m cerise_gen3d_server.manage export-jobs "/data/jobs_$TAG.json" >/dev/null \
  && sudo cp "$SRV/data/jobs_$TAG.json" "$RES/jobs_$TAG.json"
echo "[lt] $TAG fim"

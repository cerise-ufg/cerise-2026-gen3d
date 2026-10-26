#!/usr/bin/env bash
# Teste rapido no proprio Spark: envia uma imagem, acompanha o job e baixa o GLB.
# Uso: smoke.sh <imagem> [preset] [url]
IMG="$1"; PRESET="${2:-rapido}"; URL="${3:-http://127.0.0.1:8095}"
OUT=/tmp/cerise26_smoke; mkdir -p $OUT
R=$(curl -s -F "image=@${IMG}" -F "options={\"preset\":\"${PRESET}\",\"texture\":true,\"remove_background\":true}" "$URL/api/v1/jobs")
echo "POST /api/v1/jobs -> $R"
ID=$(echo "$R" | python3 -c 'import sys,json; print(json.load(sys.stdin)["job_id"])')
while true; do
  J=$(curl -s "$URL/api/v1/jobs/$ID")
  ST=$(echo "$J" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["status"], d["progress"], d["stage"], d["position"], d["eta_seconds"])')
  echo "  $(date +%T) $ST"
  case "$ST" in done*|error*|cancelled*) break;; esac
  sleep 2
done
echo "$J" | python3 -m json.tool | head -60
curl -s -o $OUT/model.glb -w "GLB: HTTP %{http_code}, %{size_download} bytes, %{content_type}\n" "$URL/api/v1/jobs/$ID/model.glb"
curl -s -o $OUT/thumbnail.png -w "PNG: HTTP %{http_code}, %{size_download} bytes\n" "$URL/api/v1/jobs/$ID/thumbnail.png"

#!/usr/bin/env bash
# Espera o /health responder status "ok" (worker com modelo carregado). Uso: wait_health.sh [timeout_s] [url]
T="${1:-500}"; URL="${2:-http://127.0.0.1:8095}"
end=$(( $(date +%s) + T ))
while [ "$(date +%s)" -lt "$end" ]; do
  S=$(curl -s --max-time 3 "$URL/api/v1/health" | python3 -c 'import sys,json; print(json.load(sys.stdin)["status"])' 2>/dev/null)
  [ "$S" = "ok" ] && { echo "health ok"; exit 0; }
  sleep 5
done
echo "timeout esperando health (ultimo: ${S:-sem resposta})"; exit 1

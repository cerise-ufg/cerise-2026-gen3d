#!/usr/bin/env bash
# Espera um padrao aparecer num arquivo (ate timeout_s). Uso: waitfor.sh <timeout_s> <arquivo> <padrao>
T="$1"; F="$2"; P="$3"
end=$(( $(date +%s) + T ))
while [ "$(date +%s)" -lt "$end" ]; do
  grep -q -- "$P" "$F" 2>/dev/null && { echo "achou: $P"; exit 0; }
  sleep 10
done
echo "timeout ($T s) esperando: $P"; exit 1

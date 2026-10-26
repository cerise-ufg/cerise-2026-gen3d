#!/usr/bin/env bash
# Amostra a memoria de GPU (por processo, nvidia-smi) dos containers do servidor 3D e a MemAvailable do host.
# Uso: bash gpu_sampler.sh <saida.csv> <container> [container...]   (para com kill)
OUT="$1"; shift
echo "t,container,pid,used_mib,mem_available_gib" > "$OUT"
while true; do
  T=$(date +%s.%N)
  AV=$(awk '/MemAvailable/ {printf "%.2f", $2/1048576}' /proc/meminfo)
  APPS=$(nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits 2>/dev/null)
  for C in "$@"; do
    PIDS=$(sudo docker top "$C" -eo pid 2>/dev/null | tail -n +2 | tr '\n' ' ')
    USED=0; P0=""
    for P in $PIDS; do
      M=$(echo "$APPS" | awk -F', ' -v p="$P" '$1==p {print $2}')
      if [ -n "$M" ]; then USED=$((USED + M)); P0="$P"; fi
    done
    echo "$T,$C,$P0,$USED,$AV" >> "$OUT"
  done
  sleep 2
done

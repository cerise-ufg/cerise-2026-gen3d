#!/usr/bin/env bash
# Estado do servidor de geracao 3D: containers, health, fila, memoria de GPU dos processos.
cd "$(dirname "$0")/.."
echo "== containers"; sudo docker ps -a --filter name=cerise26_gen3d_ --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'
echo "== health"; curl -s --max-time 3 http://127.0.0.1:8095/api/v1/health | python3 -m json.tool 2>/dev/null || echo "API sem resposta"
echo "== fila"; curl -s --max-time 3 http://127.0.0.1:8095/api/v1/queue | python3 -m json.tool 2>/dev/null | head -40
echo "== memoria"; free -g | head -2
echo "== GPU (processos)"; nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader

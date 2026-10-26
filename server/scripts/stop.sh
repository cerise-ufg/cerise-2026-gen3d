#!/usr/bin/env bash
# Para o servidor de geracao 3D (parada graciosa: o worker termina o job em andamento, ate 150 s).
# Os jobs na fila ficam no SQLite (data/gen3d.sqlite3) e continuam quando o servico subir de novo.
set -euo pipefail
cd "$(dirname "$0")/.."
sudo docker compose -f compose.yaml down
sudo docker ps --format '{{.Names}}' | grep -E '^cerise26_gen3d_(api|worker)' || echo "[stop] containers do servidor parados"

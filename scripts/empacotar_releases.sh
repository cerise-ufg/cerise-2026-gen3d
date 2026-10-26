#!/bin/bash
# (Spark) Empacota as saidas brutas de ~/cerise2026/gen3d nos arquivos publicados nos Releases (ver RELEASES.md).
# Somente le as pastas de origem; grava em ~/cerise2026/gen3d/_orgstg. Usa nice para nao disputar CPU com a producao.
set -u
G=${G:-$HOME/cerise2026/gen3d}
O=$G/_orgstg
mkdir -p "$O"
cd "$G" || exit 1

# copia consistente do banco SQLite do servidor (WAL ativo), sem parar o servico
sudo python3 - "$G" <<'PY'
import sqlite3, sys
g = sys.argv[1]
src = sqlite3.connect(f'file:{g}/server/data/gen3d.sqlite3?mode=ro', uri=True)
dst = sqlite3.connect(f'{g}/_orgstg/gen3d_snapshot.sqlite3')
src.backup(dst)
dst.close(); src.close()
PY

sudo nice -n 19 tar czf "$O/gen3d_results_bench.tar.gz" results/bench
sudo nice -n 19 tar czf "$O/gen3d_results_a3_a3i.tar.gz" results/a3 results/a3i
sudo nice -n 19 tar czf "$O/gen3d_results_presets.tar.gz" results/presets
sudo nice -n 19 tar czf "$O/gen3d_results_a4_test.tar.gz" results/a4_pytest results/test
sudo nice -n 19 tar czf "$O/gen3d_dados_gso_cc0.tar.gz" data
sudo nice -n 19 tar czf "$O/gen3d_servidor_brutos.tar.gz" \
  --exclude='server/data/gen3d.sqlite3' --exclude='server/data/gen3d.sqlite3-wal' --exclude='server/data/gen3d.sqlite3-shm' \
  --exclude='server/data/PAUSE' \
  server/results server/data server/loadtest/pool server/results_baseline_run.log \
  --transform 's|^_orgstg/gen3d_snapshot.sqlite3|server/data/gen3d.sqlite3|' _orgstg/gen3d_snapshot.sqlite3

sudo chown -R "$(id -u):$(id -g)" "$O"
cd "$O" && sha256sum *.tar.gz > SHA256SUMS && cat SHA256SUMS
# No Windows, as saidas do teste ponta a ponta (server/e2e_out*) foram empacotadas com:
#   tar --force-local -czf gen3d_servidor_e2e_windows.tar.gz server/e2e_out server/e2e_out_antes_png \
#       server/e2e_out_final_rapido server/e2e_out_console.txt

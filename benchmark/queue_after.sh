#!/bin/bash
# Espera nao haver nenhum run_model.py rodando e entao executa os comandos (um por argumento), em sequencia.
cd /workspace/benchmark
export HY3DGEN_MODELS=/workspace/hy3dgen_models
LOG=/workspace/logs/after.log
while pgrep -f "^python run_model.py" > /dev/null; do sleep 15; done
for cmd in "$@"; do
  echo "=== $(date -u +%FT%TZ) inicio: $cmd" >> $LOG
  bash -c "$cmd"
  echo "=== $(date -u +%FT%TZ) fim rc=$?: $cmd" >> $LOG
done
echo "AFTER_DONE" >> $LOG

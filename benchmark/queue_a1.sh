#!/bin/bash
# Fila do benchmark A1 (sequencial, para nao misturar tempos de GPU entre modelos)
cd /workspace/benchmark
export HY3DGEN_MODELS=/workspace/hy3dgen_models
LOG=/workspace/logs/a1
mkdir -p $LOG
for cfg in ${@:-triposr hy2mini_turbo hy2_turbo hy2_full hy21_shape}; do
  echo "=== $(date -u +%FT%TZ) inicio $cfg" >> $LOG/queue.log
  python run_model.py --config $cfg --out /workspace/results/bench > $LOG/$cfg.log 2>&1
  echo "=== $(date -u +%FT%TZ) fim $cfg rc=$?" >> $LOG/queue.log
done
echo "QUEUE_DONE" >> $LOG/queue.log

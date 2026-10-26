#!/bin/bash
# (host) reordena: fila A3 (em execucao) -> presets do pipeline -> hy2_full (7 obj) -> AFTER_DONE (dispara hy21 e InstantMesh)
D="sudo docker exec"
SUB=Schleich_Bald_Eagle,Schleich_African_Black_Rhino,Sonny_School_Bus,Threshold_Porcelain_Teapot_White,ACE_Coffee_Mug_Kristen_16_oz_cup,Transformers_Age_of_Extinction_Mega_1Step_Bumblebee_Figure,Vtech_Roll_Learn_Turtle
for p in $($D cerise26_gen3d_dev pgrep -f queue_after.sh); do $D cerise26_gen3d_dev kill $p; done
$D -d cerise26_gen3d_dev bash -c "until grep -q QUEUE_DONE /workspace/logs/a3/queue.log 2>/dev/null; do sleep 20; done; \
  cd /workspace/benchmark && export HY3DGEN_MODELS=/workspace/hy3dgen_models; \
  until [ -f /workspace/pipeline/PRESETS_OK ]; do sleep 20; done; \
  echo \"=== \$(date -u +%FT%TZ) inicio presets\" >> /workspace/logs/after.log; \
  python run_presets.py > /workspace/logs/presets.log 2>&1; \
  echo \"=== \$(date -u +%FT%TZ) inicio hy2_full\" >> /workspace/logs/after.log; \
  python run_model.py --config hy2_full --objects $SUB --out /workspace/results/bench > /workspace/logs/a1/hy2_full.log 2>&1; \
  echo AFTER_DONE >> /workspace/logs/after.log"
sleep 2
$D cerise26_gen3d_dev bash -c 'ps -eo pid,etime,args | grep -E "[q]ueue|[r]un_model|[Q]UEUE_DONE|[C]HAIN" | cut -c1-140'

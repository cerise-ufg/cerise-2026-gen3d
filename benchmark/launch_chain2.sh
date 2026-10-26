#!/bin/bash
# (host) interrompe o hy21_full atual (offload CPU<->GPU + num_chunks 8000: ~386 s/objeto) e agenda, para depois da
# fila atual (A3 + hy2_full), uma rodada do hy21 sem offload e com num_chunks 50000 em 3 objetos.
D="sudo docker exec"
SUB3=Schleich_Bald_Eagle,Sonny_School_Bus,Vtech_Roll_Learn_Turtle
cp ~/cerise2026/gen3d/logs/a1/hy21_full.log ~/cerise2026/gen3d/logs/a1/hy21_full_offload_tentativa1.log 2>/dev/null || \
  $D cerise26_gen3d_dev cp /workspace/logs/a1/hy21_full.log /workspace/logs/a1/hy21_full_offload_tentativa1.log
for p in $($D cerise26_gen3d_dev pgrep -f "^python run_model.py --config hy21_full"); do $D cerise26_gen3d_dev kill $p; done
$D -d cerise26_gen3d_dev bash -c "until grep -q AFTER_DONE /workspace/logs/after.log; do sleep 20; done; \
  cd /workspace/benchmark && export HY3DGEN_MODELS=/workspace/hy3dgen_models && \
  echo \"=== \$(date -u +%FT%TZ) inicio hy21_full (sem offload)\" >> /workspace/logs/chain2.log && \
  python run_model.py --config hy21_full --override '{\"offload_shape\": false, \"num_chunks\": 50000}' --objects $SUB3 --out /workspace/results/bench > /workspace/logs/a1/hy21_full.log 2>&1; \
  echo \"=== \$(date -u +%FT%TZ) fim hy21_full\" >> /workspace/logs/chain2.log; echo CHAIN2_DONE >> /workspace/logs/chain2.log"
sleep 3
$D cerise26_gen3d_dev bash -c 'ps -eo pid,etime,args | grep -E "[q]ueue|[r]un_model|[A]FTER_DONE" | cut -c1-160'

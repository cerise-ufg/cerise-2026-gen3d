#!/bin/bash
# (Spark) empacota os resultados leves (sem GLB/pesos) para trazer ao espelho local
cd /home/energiainteligente/cerise2026/gen3d || exit 1
sudo rm -f /tmp/gen3d_light.tgz
sudo tar czf /tmp/gen3d_light.tgz --exclude='*.glb' --exclude='*.obj' --exclude='*.npy' --exclude='*.ply' \
  --exclude='*.jpg' --exclude='_warmup*' \
  evidencias resultados logs/a1 logs/a3 logs/*.log logs/*.out logs/*.txt \
  $(ls -d results/bench/*/summary.json results/bench/*/metrics.csv results/a3/*/summary.json results/a3/*/metrics.csv \
        results/a3i/*/summary.json results/a3i/*/metrics.csv results/presets/*/summary.json results/presets/*/metrics.csv \
        results/presets/pipeline_load*.json results/a4_pytest READY.json data/eval/index.json 2>/dev/null)
sudo chmod 644 /tmp/gen3d_light.tgz
ls -la /tmp/gen3d_light.tgz

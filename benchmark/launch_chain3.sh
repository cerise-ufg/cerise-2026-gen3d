#!/bin/bash
# (host) agenda nova rodada do InstantMesh (correcao da cor por vertice) depois do chain2 (hy21)
D="sudo docker exec"
$D cerise26_gen3d_dev bash -c "mv /workspace/results/bench/instantmesh /workspace/results/bench/instantmesh_corbranca_t1 2>/dev/null; true"
$D -d cerise26_gen3d_dev bash -c "until grep -q CHAIN2_DONE /workspace/logs/chain2.log 2>/dev/null; do sleep 20; done; \
  cd /workspace/benchmark && echo \"=== \$(date -u +%FT%TZ) inicio instantmesh v2\" >> /workspace/logs/chain3.log && \
  python run_model.py --config instantmesh --out /workspace/results/bench > /workspace/logs/a1/instantmesh.log 2>&1; \
  python evaluate.py --tags instantmesh > /workspace/logs/eval_instantmesh.log 2>&1; \
  echo CHAIN3_DONE >> /workspace/logs/chain3.log"
sleep 2
$D cerise26_gen3d_dev bash -c 'ps -eo pid,etime,args | grep -E "[C]HAIN" | cut -c1-120'

#!/bin/bash
# (host) para a fila antiga (job a3_noflashvdm em execucao + esperas encadeadas) por causa da producao religada,
# preserva os resultados parciais e inicia a fila protegida (chain_guarded.sh) destacada.
C=cerise26_gen3d_dev
for pat in "AFTER_DONE" "CHAIN2_DONE" "CHAIN3_DONE" "QUEUE_DONE" "queue_a3.sh" "queue_after.sh"; do
  for p in $(sudo docker exec $C pgrep -f "$pat"); do sudo docker exec $C kill $p 2>/dev/null; done
done
sudo docker exec $C pkill -f "^python run_model.py" ; sleep 3
sudo docker exec $C bash -c 'echo "=== $(date -u +%FT%TZ) a3_noflashvdm INTERROMPIDO (producao religou; memoria)" >> /workspace/logs/a3/queue.log'
sudo docker exec $C bash -c 'ps -eo pid,args | grep -E "[p]ython|[b]ash -c" | cut -c1-100'
free -g | sed -n 2p
setsid nohup bash ~/cerise2026/gen3d/benchmark/chain_guarded.sh > ~/cerise2026/gen3d/logs/chain_guarded.out 2>&1 < /dev/null &
sleep 2; tail -3 ~/cerise2026/gen3d/logs/chain_guarded.log

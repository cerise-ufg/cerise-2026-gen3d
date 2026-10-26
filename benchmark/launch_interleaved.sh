#!/bin/bash
# (host) depois da fila A3 sequencial: roda o A3 intercalado e libera os presets (PRESETS_OK)
SUB=Schleich_Bald_Eagle,Schleich_African_Black_Rhino,Sonny_School_Bus,ACE_Coffee_Mug_Kristen_16_oz_cup,Vtech_Roll_Learn_Turtle
VAR=i_base,i_fastpost,i_oct256,i_faces20k,i_tex1024,i_rapido,i_padrao
for p in $(sudo docker exec cerise26_gen3d_dev pgrep -f "a3_interleaved.py --objects"); do sudo docker exec cerise26_gen3d_dev kill $p; done
sudo docker exec -d cerise26_gen3d_dev bash -c "until grep -q QUEUE_DONE /workspace/logs/a3/queue.log 2>/dev/null; do sleep 15; done; \
  cd /workspace/benchmark && export HY3DGEN_MODELS=/workspace/hy3dgen_models && \
  python a3_interleaved.py --objects $SUB --variants $VAR > /workspace/logs/a3/interleaved.log 2>&1; \
  touch /workspace/pipeline/PRESETS_OK"
sleep 1
sudo docker exec cerise26_gen3d_dev bash -c 'ps -eo pid,etime,args | grep -E "[i]nterleaved|[Q]UEUE_DONE" | cut -c1-120'

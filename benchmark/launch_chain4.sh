#!/bin/bash
# (host) depois do chain3 (InstantMesh): repete a variante bf16 (com a correcao do marching cubes)
OBJS=Schleich_Bald_Eagle,Schleich_African_Black_Rhino,Sonny_School_Bus,Threshold_Porcelain_Teapot_White,ACE_Coffee_Mug_Kristen_16_oz_cup,Transformers_Age_of_Extinction_Mega_1Step_Bumblebee_Figure,Vtech_Roll_Learn_Turtle
sudo docker exec -d cerise26_gen3d_dev bash -c "until grep -q CHAIN3_DONE /workspace/logs/chain3.log 2>/dev/null; do sleep 20; done; \
  cd /workspace/benchmark && export HY3DGEN_MODELS=/workspace/hy3dgen_models && \
  mv /workspace/logs/a3/a3_bf16.log /workspace/logs/a3/a3_bf16_falha_numpy.log; \
  python run_model.py --config hy2_turbo --override '{\"shape_dtype\": \"bf16\"}' --tag a3_bf16 --objects $OBJS --out /workspace/results/a3 > /workspace/logs/a3/a3_bf16.log 2>&1; \
  echo CHAIN4_DONE >> /workspace/logs/chain3.log"

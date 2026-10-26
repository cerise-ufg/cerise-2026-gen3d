#!/bin/bash
# (executado no host) encerra a fila A1 antiga (o processo em execucao continua) e agenda o restante do A1.
SUB=Schleich_Bald_Eagle,Schleich_African_Black_Rhino,Sonny_School_Bus,Threshold_Porcelain_Teapot_White,ACE_Coffee_Mug_Kristen_16_oz_cup,Transformers_Age_of_Extinction_Mega_1Step_Bumblebee_Figure,Vtech_Roll_Learn_Turtle
D="sudo docker exec"
for p in $($D cerise26_gen3d_dev pgrep -f queue_a1.sh); do $D cerise26_gen3d_dev kill $p; done
$D -d cerise26_gen3d_dev bash /workspace/benchmark/queue_after.sh \
  "python run_model.py --config instantmesh --out /workspace/results/bench > /workspace/logs/a1/instantmesh.log 2>&1" \
  "python run_model.py --config hy21_full --objects $SUB --out /workspace/results/bench > /workspace/logs/a1/hy21_full.log 2>&1" \
  "python run_model.py --config hy2_full --objects $SUB --out /workspace/results/bench > /workspace/logs/a1/hy2_full.log 2>&1"
sleep 2
$D cerise26_gen3d_dev bash -c 'ps -eo pid,args | grep -E "[q]ueue|[r]un_model" | cut -c1-150'

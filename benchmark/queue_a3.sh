#!/bin/bash
# Fila A3: variantes de otimizacao sobre a base escolhida (um fator por vez), subconjunto de 7 objetos.
# Uso: queue_a3.sh <config_base>   (ex.: hy2mini_turbo)
cd /workspace/benchmark
export HY3DGEN_MODELS=/workspace/hy3dgen_models
BASE=${1:-hy2mini_turbo}
OBJS=Schleich_Bald_Eagle,Schleich_African_Black_Rhino,Sonny_School_Bus,Threshold_Porcelain_Teapot_White,ACE_Coffee_Mug_Kristen_16_oz_cup,Transformers_Age_of_Extinction_Mega_1Step_Bumblebee_Figure,Vtech_Roll_Learn_Turtle
LOG=/workspace/logs/a3; mkdir -p $LOG
# tag | override JSON
VARIANTS=(
  'a3_base|{}'
  'a3_fastpost|{"remove_floaters": false, "decimator": "fast"}'
  'a3_oct256|{"octree": 256}'
  'a3_faces20k|{"max_faces": 20000}'
  'a3_faces10k|{"max_faces": 10000}'
  'a3_tex1024|{"texture_size": 1024, "render_size": 1024}'
  'a3_paintfull|{"paint": "hunyuan3d-paint-v2-0"}'
  'a3_steps10|{"steps": 10}'
  'a3_bf16|{"shape_dtype": "bf16"}'
  'a3_noflashvdm|{"flashvdm": false}'
)
for v in "${VARIANTS[@]}"; do
  tag=${v%%|*}; ov=${v#*|}
  [ -n "$ONLY" ] && [[ ",$ONLY," != *",$tag,"* ]] && continue
  echo "=== $(date -u +%FT%TZ) inicio $tag $ov" >> $LOG/queue.log
  python run_model.py --config $BASE --override "$ov" --tag $tag --objects $OBJS --out /workspace/results/a3 > $LOG/$tag.log 2>&1
  echo "=== $(date -u +%FT%TZ) fim $tag rc=$?" >> $LOG/queue.log
done
echo "QUEUE_DONE" >> $LOG/queue.log

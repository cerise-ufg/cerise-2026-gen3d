#!/bin/bash
cd /workspace/benchmark
python aggregate.py --tags triposr,instantmesh,hy2mini_turbo,hy2_turbo,hy2_full,hy21_full --prefix a1 \
  --title "Benchmark A1 — GSO, DGX Spark GB10" > /dev/null 2>&1
python aggregate.py --bench /workspace/results/presets --tags preset_rapido,preset_padrao,preset_alto --prefix presets \
  --labels "rápido;padrão;alto" --title "Presets do pipeline (GSO + fotos reais)" > /dev/null 2>&1
G="Schleich_Bald_Eagle,Sonny_School_Bus,ACE_Coffee_Mug_Kristen_16_oz_cup,Vtech_Roll_Learn_Turtle,Schleich_African_Black_Rhino,Transformers_Age_of_Extinction_Mega_1Step_Bumblebee_Figure"
LBL="TripoSR,InstantMesh,H3D-2mini-T,H3D-2-Turbo,H3D-2.0 padrão,H3D-2.1 PBR"
python grid_compare.py --tags triposr,instantmesh,hy2mini_turbo,hy2_turbo,hy2_full,hy21_full --labels "$LBL" --objects $G \
  --out /workspace/evidencias/a1_grade_entrada.png --cell 190
python grid_compare.py --tags triposr,instantmesh,hy2mini_turbo,hy2_turbo,hy2_full,hy21_full --labels "$LBL" --objects $G \
  --only-novel --out /workspace/evidencias/a1_grade_vista_nova.png --cell 190

#!/bin/bash
# (container) agregacoes finais: tabelas + graficos A1, A3 (sequencial e intercalado), presets e grades A1.
cd /workspace/benchmark
export HY3DGEN_MODELS=/workspace/hy3dgen_models
B=/workspace/results/bench
# garante avaliacao (pula o que ja foi avaliado)
python evaluate.py --tags triposr,instantmesh,hy2mini_turbo,hy2_turbo,hy2_full,hy21_full --skip-existing > /workspace/logs/eval_fin_a1.log 2>&1
python evaluate.py --results /workspace/results/a3 --tags a3_base,a3_fastpost,a3_oct256,a3_faces20k,a3_faces10k,a3_tex1024,a3_paintfull,a3_steps10,a3_bf16,a3_noflashvdm --skip-existing > /workspace/logs/eval_fin_a3.log 2>&1
python evaluate.py --results /workspace/results/presets --tags preset_rapido,preset_padrao,preset_alto --skip-existing > /workspace/logs/eval_fin_presets.log 2>&1
echo "== A1"
python aggregate.py --tags triposr,instantmesh,hy2mini_turbo,hy2_turbo,hy2_full,hy21_full --prefix a1 \
  --title "Benchmark A1 — GSO, DGX Spark GB10" 2>&1 | grep -E "^\||ignorado"
echo "== A3 sequencial"
python aggregate_a3.py --tags a3_base,a3_fastpost,a3_oct256,a3_faces20k,a3_faces10k,a3_tex1024,a3_paintfull,a3_steps10,a3_bf16,a3_noflashvdm 2>&1 | grep -E "^\||ignorado"
echo "== A3 intercalado"
bash eval_a3i.sh 2>&1 | grep -E "^\||ignorado"
echo "== presets"
python aggregate.py --bench /workspace/results/presets --tags preset_rapido,preset_padrao,preset_alto --prefix presets \
  --labels "rápido;padrão;alto" --title "Presets do pipeline (GSO + fotos reais)" 2>&1 | grep -E "^\||ignorado"
echo "== grades A1"
G="Schleich_Bald_Eagle,Sonny_School_Bus,ACE_Coffee_Mug_Kristen_16_oz_cup,Vtech_Roll_Learn_Turtle,Schleich_African_Black_Rhino,Transformers_Age_of_Extinction_Mega_1Step_Bumblebee_Figure"
LBL="TripoSR,InstantMesh,H3D-2mini-T,H3D-2-Turbo,H3D-2.0 padrão,H3D-2.1 PBR"
python grid_compare.py --tags triposr,instantmesh,hy2mini_turbo,hy2_turbo,hy2_full,hy21_full --labels "$LBL" --objects $G \
  --out /workspace/evidencias/a1_grade_entrada.png --cell 190
python grid_compare.py --tags triposr,instantmesh,hy2mini_turbo,hy2_turbo,hy2_full,hy21_full --labels "$LBL" --objects $G \
  --only-novel --out /workspace/evidencias/a1_grade_vista_nova.png --cell 190
echo FINAL_AGG_FIM

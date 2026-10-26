#!/bin/bash
# A4 (dentro do container): pytest do pipeline, carregamento no model-viewer/three.js, grades qualitativas e tabela
# de compressao. Rodar so com >= 30 GB "available" no host (pipeline com os 3 presets ~ 18-20 GB).
cd /workspace
export HY3DGEN_MODELS=/workspace/hy3dgen_models PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
mkdir -p results/a4_pytest evidencias/viewer resultados
P=results/presets
step=${1:-all}

if [ "$step" = all ] || [ "$step" = pytest ]; then
  # GEN3D_TEST_PRESETS controla os presets (o pipeline so carrega os paints necessarios); JUNIT_NAME o arquivo
  J=${JUNIT_NAME:-all}
  python -m pytest -v -p no:cacheprovider validation/test_pipeline.py --junitxml=results/a4_pytest/junit_$J.xml \
    > results/a4_pytest/pytest_output_$J.txt 2>&1
  echo "PYTEST_RC=$?" >> results/a4_pytest/pytest_output_$J.txt
fi

if [ "$step" = all ] || [ "$step" = viewer ]; then
  GLBS=""
  for o in Sonny_School_Bus Schleich_Bald_Eagle Vtech_Roll_Learn_Turtle cc0_duck cc0_rooster; do
    [ -f $P/preset_padrao/$o/model.glb ] && GLBS="$GLBS $P/preset_padrao/$o/model.glb"
  done
  [ -f $P/preset_rapido/ACE_Coffee_Mug_Kristen_16_oz_cup/model.glb ] && GLBS="$GLBS $P/preset_rapido/ACE_Coffee_Mug_Kristen_16_oz_cup/model.glb"
  [ -f $P/preset_alto/Transformers_Age_of_Extinction_Mega_1Step_Bumblebee_Figure/model.glb ] && GLBS="$GLBS $P/preset_alto/Transformers_Age_of_Extinction_Mega_1Step_Bumblebee_Figure/model.glb"
  rm -rf /tmp/viewer_site
  python validation/viewer_check.py --out evidencias/viewer --glbs $GLBS > results/a4_pytest/viewer_output.txt 2>&1
fi

if [ "$step" = all ] || [ "$step" = grids ]; then
  python validation/qual_grid.py --root $P/preset_padrao --out evidencias/a4_grade_gso_padrao.png \
    --objects Schleich_Bald_Eagle,Sonny_School_Bus,Vtech_Roll_Learn_Turtle,ACE_Coffee_Mug_Kristen_16_oz_cup,Breyer_Horse_Of_The_Year_2015,Reebok_ZIGLITE_RUSH,Transformers_Age_of_Extinction_Mega_1Step_Bumblebee_Figure,Vtech_Stack_Sing_Rings_636_Months
  python validation/qual_grid.py --root $P/preset_padrao --out evidencias/a4_grade_fotos_reais.png \
    --objects cc0_duck,cc0_rooster,cc0_donkey,cc0_cat,cc0_teapot,cc0_angular_teapot
  python validation/qual_grid.py --root $P/preset_alto --out evidencias/a4_grade_gso_alto.png \
    --objects Schleich_Bald_Eagle,Sonny_School_Bus,Vtech_Roll_Learn_Turtle,ACE_Coffee_Mug_Kristen_16_oz_cup
fi

if [ "$step" = all ] || [ "$step" = compress ]; then
  python benchmark/compression_table.py --root $P/preset_padrao --out-json resultados/a3_compressao.json \
    --out-png evidencias/a3_compressao.png > results/a4_pytest/compress_output.txt 2>&1
fi
echo A4_FIM

#!/bin/bash
# Etapa 3: dependencias do InstantMesh e do Hunyuan3D-2.1 (paint PBR)
set -x
export MAX_JOBS=4 TORCH_CUDA_ARCH_LIST="12.1"
PIP="nice -n 19 pip install --no-cache-dir"
$PIP "pytorch-lightning>=2.1,<2.6" PyMCubes torchmetrics
# Hunyuan3D-2.1 hy3dpaint: realesrgan/basicsr (super-resolucao das vistas), configargparse
$PIP --no-deps basicsr==1.4.2 realesrgan==0.3.0 facexlib gfpgan
$PIP addict future lmdb yapf tb-nightly configargparse filterpy numba
python - <<'EOF'
import importlib
for m in ["pytorch_lightning","mcubes","basicsr","realesrgan"]:
    try:
        importlib.import_module(m); print("OK ", m)
    except Exception as e:
        print("ERR", m, repr(e)[:300])
EOF

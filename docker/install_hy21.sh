#!/bin/bash
# Hunyuan3D-2.1 (paint PBR): extensoes compiladas no proprio diretorio (sem conflitar com o custom_rasterizer do 2.0)
set -x
export MAX_JOBS=4 TORCH_CUDA_ARCH_LIST="12.1"
H=${TP:-/workspace/third_party}/Hunyuan3D-2.1/hy3dpaint
cd $H/custom_rasterizer && nice -n 19 python setup.py build_ext --inplace; echo "CR21_RC=$?"
ls $H/custom_rasterizer/*.so
cd $H/DifferentiableRenderer && nice -n 19 bash compile_mesh_painter.sh; echo "MIP_RC=$?"
ls $H/DifferentiableRenderer/*.so
mkdir -p /workspace/weights
[ -f /workspace/weights/RealESRGAN_x4plus.pth ] || curl -sL -o /workspace/weights/RealESRGAN_x4plus.pth \
  https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth
ls -la /workspace/weights
python -c "
from huggingface_hub import snapshot_download
print(snapshot_download('facebook/dinov2-giant', allow_patterns=['config.json','preprocessor_config.json','model.safetensors']))"

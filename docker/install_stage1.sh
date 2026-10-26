#!/bin/bash
# Etapa 1: dependencias Python comuns (rodar dentro do container base nvcr.io/nvidia/pytorch:26.05-py3)
set -e
export MAX_JOBS=4
export TORCH_CUDA_ARCH_LIST="12.1"
PIP="nice -n 19 pip install --no-cache-dir"
$PIP "transformers==4.46.3" "diffusers==0.31.0" "accelerate>=1.1" "huggingface_hub<1.0" safetensors \
     omegaconf einops tqdm trimesh pygltflib xatlas opencv-python-headless scikit-image imageio \
     "rembg==2.0.65" onnxruntime pytest matplotlib pandas jaxtyping plyfile timm open_clip_torch \
     fast-simplification rtree pillow
$PIP pymeshlab || echo "PYMESHLAB_FAIL"
python - <<'EOF'
import importlib
for m in ["torch","transformers","diffusers","trimesh","pygltflib","xatlas","cv2","skimage","rembg","onnxruntime","pymeshlab","fast_simplification","open_clip","timm"]:
    try:
        mod = importlib.import_module(m); print("OK ", m, getattr(mod, "__version__", ""))
    except Exception as e:
        print("ERR", m, repr(e)[:200])
EOF

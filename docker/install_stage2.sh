#!/bin/bash
# Etapa 2: libs de sistema + extensoes CUDA/C++ (Hunyuan3D-2 texgen, nvdiffrast, torchmcubes) para sm_121
set -x
export MAX_JOBS=4
export TORCH_CUDA_ARCH_LIST="12.1"
export DEBIAN_FRONTEND=noninteractive
TP=${TP:-/workspace/third_party}
apt-get update -qq && apt-get install -y -qq libgl1 libglib2.0-0 libegl1 libgles2 libopengl0 libxrender1 libxext6 libsm6 unzip > /dev/null
python -c "import pymeshlab; print('pymeshlab OK', pymeshlab.__version__ if hasattr(pymeshlab,'__version__') else '')"

# --- Hunyuan3D-2: rasterizador customizado (CUDA) ---
cd $TP/Hunyuan3D-2/hy3dgen/texgen/custom_rasterizer && nice -n 19 pip install --no-build-isolation --no-cache-dir . ; echo "CUSTOM_RASTERIZER_RC=$?"
# --- Hunyuan3D-2: differentiable_renderer (pybind11, CPU) ---
cd $TP/Hunyuan3D-2/hy3dgen/texgen/differentiable_renderer && nice -n 19 python setup.py build_ext --inplace ; echo "DIFFREND_RC=$?"
ls $TP/Hunyuan3D-2/hy3dgen/texgen/differentiable_renderer/*.so
# --- nvdiffrast (renderizacao das vistas p/ benchmark) ---
cd $TP/nvdiffrast && nice -n 19 pip install --no-build-isolation --no-cache-dir . ; echo "NVDIFFRAST_RC=$?"
# --- torchmcubes (TripoSR) ---
cd $TP/torchmcubes && nice -n 19 pip install --no-build-isolation --no-cache-dir . ; echo "TORCHMCUBES_RC=$?"
python - <<'EOF'
import importlib
for m in ["pymeshlab","custom_rasterizer","nvdiffrast.torch","torchmcubes"]:
    try:
        importlib.import_module(m); print("OK ", m)
    except Exception as e:
        print("ERR", m, repr(e)[:300])
EOF

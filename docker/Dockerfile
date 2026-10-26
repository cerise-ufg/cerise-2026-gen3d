# CERISE 2026 - Geracao 3D (imagem -> GLB texturizado) para DGX Spark (GB10, sm_121, aarch64)
# Build (no Spark, a partir de ~/cerise2026/gen3d):
#   sudo docker build -f docker/Dockerfile -t cerise26_gen3d:latest .
# Execucao: ver README.md / READY.json (monta o cache HF e a arvore de pesos do hy3dgen).
FROM nvcr.io/nvidia/pytorch:26.05-py3

ENV DEBIAN_FRONTEND=noninteractive \
    TORCH_CUDA_ARCH_LIST="12.1" \
    MAX_JOBS=4 \
    HY3DGEN_MODELS=/opt/gen3d/hy3dgen_models \
    HY2_ROOT=/opt/gen3d/third_party/Hunyuan3D-2 \
    TP=/opt/gen3d/third_party \
    GLTF_TOOLS=/opt/gltf-tools/node_modules/.bin \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      libgl1 libglib2.0-0 libegl1 libgles2 libopengl0 libxrender1 libxext6 libsm6 unzip \
      libharfbuzz0b libfontconfig1 libfreetype6 libxkbcommon0 libdbus-1-3 libx11-6 libxcb1 libgomp1 libtbb12 \
      xz-utils curl \
    && rm -rf /var/lib/apt/lists/*

# Node 22 LTS oficial (o sharp usado pelo glTF-Transform exige Node >= 20; o nodejs do apt e 18)
RUN curl -sL https://nodejs.org/dist/v22.11.0/node-v22.11.0-linux-arm64.tar.xz | tar xJ -C /opt && \
    ln -sf /opt/node-v22.11.0-linux-arm64/bin/node /usr/local/bin/node && \
    ln -sf /opt/node-v22.11.0-linux-arm64/bin/npm /usr/local/bin/npm && \
    ln -sf /opt/node-v22.11.0-linux-arm64/bin/npx /usr/local/bin/npx

# dependencias Python (torch/torchvision vem da imagem base NGC e ficam fixos pelo PIP_CONSTRAINT)
RUN pip install --no-cache-dir "transformers==4.46.3" "diffusers==0.31.0" "accelerate>=1.1" "huggingface_hub<1.0" \
      safetensors omegaconf einops tqdm trimesh pygltflib xatlas opencv-python-headless scikit-image imageio \
      "rembg==2.0.65" onnxruntime pytest matplotlib pandas jaxtyping plyfile timm open_clip_torch \
      fast-simplification rtree pillow pymeshlab scikit-build-core cmake "pytorch-lightning>=2.1,<2.6" PyMCubes \
      flask waitress

# ferramentas glTF (pos-processamento/validacao): glTF-Transform, gltfpack (wasm), Khronos glTF-Validator
RUN mkdir -p /opt/gltf-tools && cd /opt/gltf-tools && npm init -y >/dev/null && \
    npm install --no-audit --no-fund --include=optional @gltf-transform/cli@4 gltfpack gltf-validator && \
    node -e "require('sharp'); console.log('sharp ok')"

# fontes oficiais dos modelos usados pelo pipeline + extensoes CUDA/C++ compiladas para sm_121
COPY third_party/Hunyuan3D-2 /opt/gen3d/third_party/Hunyuan3D-2
COPY third_party/nvdiffrast /opt/gen3d/third_party/nvdiffrast
RUN cd /opt/gen3d/third_party/Hunyuan3D-2/hy3dgen/texgen/custom_rasterizer && \
      rm -rf build *.egg-info && pip install --no-build-isolation --no-cache-dir . && \
    cd ../differentiable_renderer && rm -rf build && python setup.py build_ext --inplace && \
    cd /opt/gen3d/third_party/nvdiffrast && pip install --no-build-isolation --no-cache-dir .

# codigo da frente (pipeline + executores + benchmark + testes)
COPY pipeline /opt/gen3d/pipeline
COPY models /opt/gen3d/models
COPY benchmark /opt/gen3d/benchmark
COPY validation /opt/gen3d/validation

WORKDIR /opt/gen3d
CMD ["python", "-c", "import sys; sys.path.insert(0,'pipeline'); import gen3d_pipeline; print('cerise26_gen3d ok')"]

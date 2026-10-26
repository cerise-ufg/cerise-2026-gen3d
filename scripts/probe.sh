#!/bin/bash
mkdir -p ~/cerise2026/gen3d ~/cerise2026/hf_cache
ls -la ~/cerise2026
ls ~/.cache/huggingface 2>&1 | head
test -f ~/.cache/huggingface/token && echo "HAS HF TOKEN (host)" || echo "no host hf token"
test -f ~/cerise2026/hf_cache/token && echo "HAS HF TOKEN (shared cache)" || echo "no shared hf token"
sudo docker run --rm --gpus all --ipc=host nvcr.io/nvidia/pytorch:26.05-py3 bash -c '
python -c "import torch,sys;print(sys.version);print(torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0)); print(torch.cuda.get_arch_list())"
pip list 2>/dev/null | grep -iE "^(torch|numpy|opencv|transformers|diffusers|pillow|scipy|scikit|trimesh|onnx|ninja|pybind|einops|timm|huggingface|accelerate|xformers|flash|triton)"
echo PIP_CONSTRAINT=$PIP_CONSTRAINT
cat /etc/pip/constraint.txt 2>/dev/null | head -50
nvcc --version | tail -2
'

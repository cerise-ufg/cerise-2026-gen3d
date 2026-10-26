"""O UNet do paint-v2-0-turbo em .safetensors traz chaves de IP-Adapter que o modules.py oficial nao cria;
o .bin oficial (fp32) e o arquivo que o carregador espera. Baixa o .bin e substitui o convertido."""
import os

from huggingface_hub import hf_hub_download

ROOT = os.environ.get("HY3DGEN_MODELS", "/workspace/hy3dgen_models")
p = hf_hub_download("tencent/Hunyuan3D-2", "hunyuan3d-paint-v2-0-turbo/unet/diffusion_pytorch_model.bin")
dst = os.path.join(ROOT, "tencent/Hunyuan3D-2/hunyuan3d-paint-v2-0-turbo/unet/diffusion_pytorch_model.bin")
if os.path.lexists(dst):
    os.remove(dst)
os.symlink(p, dst)
print("ok", dst, "->", p)

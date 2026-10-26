"""Monta HY3DGEN_MODELS/tencent/Hunyuan3D-2 com links para o cache HF e converte os UNets do paint de
.safetensors para .bin (o carregador do repositorio, unet/modules.py, so aceita diffusion_pytorch_model.bin).
Evita baixar os .bin oficiais (3,7 GB + 7,3 GB) que tem o mesmo conteudo."""
import glob
import os
import shutil

import torch
from safetensors.torch import load_file

ROOT = os.environ.get("HY3DGEN_MODELS", "/workspace/hy3dgen_models")
HF = "/root/.cache/huggingface/hub"


def snapshot(repo):
    d = glob.glob(f"{HF}/models--{repo.replace('/', '--')}/snapshots/*")
    return d[0]


def main():
    snap = snapshot("tencent/Hunyuan3D-2")
    dst = os.path.join(ROOT, "tencent", "Hunyuan3D-2")
    if os.path.islink(dst):
        os.remove(dst)
    os.makedirs(dst, exist_ok=True)
    for sub in sorted(os.listdir(snap)):
        s, d = os.path.join(snap, sub), os.path.join(dst, sub)
        if sub.startswith("hunyuan3d-paint"):
            os.makedirs(d, exist_ok=True)
            for item in os.listdir(s):
                si, di = os.path.join(s, item), os.path.join(d, item)
                if item == "unet":
                    os.makedirs(di, exist_ok=True)
                    for f in os.listdir(si):
                        if not os.path.lexists(os.path.join(di, f)):
                            os.symlink(os.path.join(si, f), os.path.join(di, f))
                    binp = os.path.join(di, "diffusion_pytorch_model.bin")
                    if not os.path.exists(binp):
                        sd = load_file(os.path.join(si, "diffusion_pytorch_model.safetensors"))
                        torch.save(sd, binp)
                        print("convertido", binp, len(sd), "tensores")
                elif not os.path.lexists(di):
                    os.symlink(si, di)
        elif not os.path.lexists(d):
            os.symlink(s, d)
    print("ok", dst, os.listdir(dst))


if __name__ == "__main__":
    main()

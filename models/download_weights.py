"""Baixa SOMENTE os arquivos de pesos necessarios (evita duplicatas .bin/.ckpt/.safetensors dos repositorios HF)
e cria a arvore local esperada pelo hy3dgen (HY3DGEN_MODELS/<repo>/<subpasta>) via links simbolicos para o cache HF."""
import argparse
import os

from huggingface_hub import snapshot_download

SETS = {
    "hy2": [
        ("tencent/Hunyuan3D-2", [
            "hunyuan3d-dit-v2-0/config.yaml", "hunyuan3d-dit-v2-0/model.fp16.safetensors",
            "hunyuan3d-dit-v2-0-turbo/config.yaml", "hunyuan3d-dit-v2-0-turbo/model.fp16.safetensors",
            "hunyuan3d-vae-v2-0-turbo/config.yaml", "hunyuan3d-vae-v2-0-turbo/model.fp16.safetensors",
            "hunyuan3d-delight-v2-0/*", "hunyuan3d-delight-v2-0/*/*",
            "hunyuan3d-paint-v2-0/model_index.json", "hunyuan3d-paint-v2-0/feature_extractor/*",
            "hunyuan3d-paint-v2-0/scheduler/*", "hunyuan3d-paint-v2-0/text_encoder/*", "hunyuan3d-paint-v2-0/tokenizer/*",
            "hunyuan3d-paint-v2-0/unet/config.json", "hunyuan3d-paint-v2-0/unet/modules.py",
            "hunyuan3d-paint-v2-0/unet/diffusion_pytorch_model.safetensors",
            "hunyuan3d-paint-v2-0/vae/config.json", "hunyuan3d-paint-v2-0/vae/diffusion_pytorch_model.safetensors",
            "hunyuan3d-paint-v2-0-turbo/model_index.json", "hunyuan3d-paint-v2-0-turbo/feature_extractor/*",
            "hunyuan3d-paint-v2-0-turbo/image_encoder/*", "hunyuan3d-paint-v2-0-turbo/scheduler/*",
            "hunyuan3d-paint-v2-0-turbo/text_encoder/*", "hunyuan3d-paint-v2-0-turbo/tokenizer/*",
            "hunyuan3d-paint-v2-0-turbo/unet/config.json", "hunyuan3d-paint-v2-0-turbo/unet/modules.py",
            "hunyuan3d-paint-v2-0-turbo/unet/diffusion_pytorch_model.safetensors",
            "hunyuan3d-paint-v2-0-turbo/vae/*",
        ]),
        ("tencent/Hunyuan3D-2mini", [
            "hunyuan3d-dit-v2-mini-turbo/config.yaml", "hunyuan3d-dit-v2-mini-turbo/model.fp16.safetensors",
            "hunyuan3d-vae-v2-mini-turbo/config.yaml", "hunyuan3d-vae-v2-mini-turbo/model.fp16.safetensors",
        ]),
    ],
    "hy21": [
        ("tencent/Hunyuan3D-2.1", ["hunyuan3d-dit-v2-1/*", "hunyuan3d-vae-v2-1/*", "hunyuan3d-paintpbr-v2-1/*",
                                   "hunyuan3d-paintpbr-v2-1/*/*"]),
    ],
    "triposr": [("stabilityai/TripoSR", ["config.yaml", "model.ckpt"])],
    "instantmesh": [
        ("sudo-ai/zero123plus-v1.2", ["*.json", "*/*.json", "*/*.txt", "*/*.safetensors"]),
        ("TencentARC/InstantMesh", ["diffusion_pytorch_model.bin", "instant_mesh_large.ckpt"]),
        ("facebook/dino-vitb16", ["config.json", "preprocessor_config.json", "pytorch_model.bin"]),
    ],
    "trellis": [("microsoft/TRELLIS-image-large", ["pipeline.json", "ckpts/*"])],
    "clip": [("openai/clip-vit-large-patch14", ["config.json", "preprocessor_config.json", "tokenizer*", "vocab.json",
                                                "merges.txt", "special_tokens_map.json", "model.safetensors"])],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sets", nargs="+")
    ap.add_argument("--hy3dgen-dir", default="/workspace/hy3dgen_models")
    a = ap.parse_args()
    for s in a.sets:
        for repo, pats in SETS[s]:
            p = snapshot_download(repo_id=repo, allow_patterns=pats)
            print("OK", repo, "->", p, flush=True)
            if repo.startswith("tencent/"):
                link = os.path.join(a.hy3dgen_dir, repo)
                os.makedirs(os.path.dirname(link), exist_ok=True)
                # link relativo ao ponto de montagem do cache HF no container
                if os.path.islink(link):
                    os.remove(link)
                os.symlink(p, link)
                print("   link", link, "->", p)


if __name__ == "__main__":
    main()

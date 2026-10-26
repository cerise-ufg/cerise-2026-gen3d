"""Executor do InstantMesh (TencentARC, Apache-2.0): Zero123++ v1.2 (6 vistas) + LRM esparso com FlexiCubes.
Segue o run.py oficial (configs/instant-mesh-large.yaml, 75 passos, 6 vistas), instrumentado por etapa."""
from __future__ import annotations

import os
import sys

import numpy as np
import torch
from PIL import Image

IM_ROOT = os.environ.get("IM_ROOT", "/workspace/third_party/InstantMesh")
if IM_ROOT not in sys.path:
    sys.path.insert(0, IM_ROOT)

from common import StageTimer  # noqa: E402


class InstantMeshRunner:
    def __init__(self, config="instant-mesh-large", steps=75, texmap=False, seed=42):
        from diffusers import DiffusionPipeline, EulerAncestralDiscreteScheduler
        from huggingface_hub import hf_hub_download
        from omegaconf import OmegaConf
        from src.utils.train_util import instantiate_from_config
        self.timer_load = StageTimer()
        self.cfg = dict(config=config, steps=steps, texmap=texmap, seed=seed)
        conf = OmegaConf.load(os.path.join(IM_ROOT, "configs", f"{config}.yaml"))
        self.infer_config = conf.infer_config
        with self.timer_load("load_zero123plus"):
            pipe = DiffusionPipeline.from_pretrained("sudo-ai/zero123plus-v1.2",
                                                     custom_pipeline=os.path.join(IM_ROOT, "zero123plus"),
                                                     torch_dtype=torch.float16)
            pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config,
                                                                         timestep_spacing="trailing")
            unet_ckpt = hf_hub_download("TencentARC/InstantMesh", "diffusion_pytorch_model.bin")
            pipe.unet.load_state_dict(torch.load(unet_ckpt, map_location="cpu", weights_only=False), strict=True)
            self.pipe = pipe.to("cuda")
        with self.timer_load("load_lrm"):
            model = instantiate_from_config(conf.model_config)
            ck = hf_hub_download("TencentARC/InstantMesh", f"{config.replace('-', '_')}.ckpt")
            sd = torch.load(ck, map_location="cpu", weights_only=False)["state_dict"]
            sd = {k[14:]: v for k, v in sd.items() if k.startswith("lrm_generator.")}
            model.load_state_dict(sd, strict=True)
            model = model.to("cuda")
            model.init_flexicubes_geometry("cuda", fovy=30.0)
            self.model = model.eval()

    @torch.no_grad()
    def generate(self, image_path, out_glb, T: StageTimer | None = None):
        import trimesh
        from einops import rearrange
        from torchvision.transforms import v2
        from src.utils.camera_util import get_zero123plus_input_cameras
        from src.utils.infer_util import resize_foreground
        T = T or StageTimer()
        with T("preprocess"):
            img = Image.open(image_path).convert("RGBA")
            img = resize_foreground(img, 0.85)
        with T("multiview_diffusion"):
            g = torch.Generator(device="cuda").manual_seed(self.cfg["seed"])
            mv = self.pipe(img, num_inference_steps=self.cfg["steps"], generator=g).images[0]
        with T("lrm_planes"):
            ims = torch.from_numpy(np.asarray(mv, dtype=np.float32) / 255.0).permute(2, 0, 1).contiguous().float()
            ims = rearrange(ims, "c (n h) (m w) -> (n m) c h w", n=3, m=2).unsqueeze(0).to("cuda")
            ims = v2.functional.resize(ims, 320, interpolation=3, antialias=True).clamp(0, 1)
            cams = get_zero123plus_input_cameras(batch_size=1, radius=4.0).to("cuda")
            planes = self.model.forward_planes(ims, cams)
        with T("mesh_extract_flexicubes"):
            out = self.model.extract_mesh(planes, use_texture_map=False, **self.infer_config)
            v, f, vc = out
        with T("export_glb"):
            vc = np.asarray(vc)
            if vc.dtype != np.uint8:  # extract_mesh ja devolve uint8 [0,255]; float [0,1] so por seguranca
                vc = (np.clip(vc, 0, 1) * 255).astype(np.uint8)
            mesh = trimesh.Trimesh(np.asarray(v), np.asarray(f), vertex_colors=vc, process=False)
            os.makedirs(os.path.dirname(os.path.abspath(out_glb)), exist_ok=True)
            mesh.export(out_glb)
        return dict(faces_raw=int(len(f)), times=T.t)

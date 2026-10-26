"""Executor do TripoSR (VAST-AI-Research/TripoSR, MIT), instrumentado por etapa.
Saida: malha com cor por vertice (o 'bake' de textura do repo usa moderngl/OpenGL e nao e usado aqui)."""
from __future__ import annotations

import os
import sys

import numpy as np
import torch
from PIL import Image

TSR_ROOT = os.environ.get("TSR_ROOT", "/workspace/third_party/TripoSR")
if TSR_ROOT not in sys.path:
    sys.path.insert(0, TSR_ROOT)

from common import StageTimer  # noqa: E402


class TripoSRRunner:
    def __init__(self, mc_resolution=256, foreground_ratio=0.85, chunk_size=8192):
        from tsr.system import TSR
        self.timer_load = StageTimer()
        self.cfg = dict(mc_resolution=mc_resolution, foreground_ratio=foreground_ratio, chunk_size=chunk_size)
        with self.timer_load("load_model"):
            self.model = TSR.from_pretrained("stabilityai/TripoSR", config_name="config.yaml", weight_name="model.ckpt")
            self.model.renderer.set_chunk_size(chunk_size)
            self.model.to("cuda")

    @torch.no_grad()
    def generate(self, image_path, out_glb, T: StageTimer | None = None):
        from tsr.utils import resize_foreground
        T = T or StageTimer()
        with T("preprocess"):
            image = Image.open(image_path).convert("RGBA")
            image = resize_foreground(image, self.cfg["foreground_ratio"])
            im = np.array(image).astype(np.float32) / 255.0
            im = im[:, :, :3] * im[:, :, 3:4] + (1 - im[:, :, 3:4]) * 0.5
            im = Image.fromarray((im * 255.0).astype(np.uint8))
        with T("triplane_forward"):
            scene_codes = self.model([im], device="cuda")
        with T("mesh_extract_mc"):
            mesh = self.model.extract_mesh(scene_codes, True, resolution=self.cfg["mc_resolution"])[0]
        with T("export_glb"):
            os.makedirs(os.path.dirname(os.path.abspath(out_glb)), exist_ok=True)
            mesh.export(out_glb)
        return dict(faces_raw=int(len(mesh.faces)), times=T.t)

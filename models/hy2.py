"""Executor da familia Hunyuan3D-2 (forma: 2.0 / 2.0-turbo / 2mini / 2mini-turbo / 2.1; textura: paint-v2-0 / turbo).

Instrumentado por etapa. Requer o pacote `hy3dgen` (repo oficial Tencent-Hunyuan/Hunyuan3D-2) no PYTHONPATH,
com as extensoes custom_rasterizer e differentiable_renderer compiladas.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import torch
from PIL import Image

HY2_ROOT = os.environ.get("HY2_ROOT", "/workspace/third_party/Hunyuan3D-2")
if HY2_ROOT not in sys.path:
    sys.path.insert(0, HY2_ROOT)

from common import StageTimer  # noqa: E402

SHAPE_MODELS = {
    # nome: (repo, subfolder, passos padrao, guidance, flashvdm)
    "dit-v2-0": ("tencent/Hunyuan3D-2", "hunyuan3d-dit-v2-0", 50, 5.0),
    "dit-v2-0-turbo": ("tencent/Hunyuan3D-2", "hunyuan3d-dit-v2-0-turbo", 5, 5.0),
    "dit-v2-0-fast": ("tencent/Hunyuan3D-2", "hunyuan3d-dit-v2-0-fast", 50, 5.0),
    "dit-v2-mini": ("tencent/Hunyuan3D-2mini", "hunyuan3d-dit-v2-mini", 50, 5.0),
    "dit-v2-mini-turbo": ("tencent/Hunyuan3D-2mini", "hunyuan3d-dit-v2-mini-turbo", 5, 5.0),
    "dit-v2-1": ("tencent/Hunyuan3D-2.1", "hunyuan3d-dit-v2-1", 50, 5.0),
}


def fast_decimate(mesh, max_faces, keep_largest=False):
    """Decimacao quadrica com fast-simplification (C++/Cython, sem pymeshlab). Opcionalmente mantem so os
    componentes grandes (remocao de 'flutuantes' barata)."""
    import fast_simplification
    import trimesh
    if keep_largest:
        comps = mesh.split(only_watertight=False)
        if len(comps) > 1:
            areas = np.array([cc.area for cc in comps])
            mesh = trimesh.util.concatenate([cc for cc, a in zip(comps, areas) if a >= 0.01 * areas.max()])
    ratio = 1.0 - max_faces / max(len(mesh.faces), 1)
    v, f = fast_simplification.simplify(np.asarray(mesh.vertices, np.float32), np.asarray(mesh.faces, np.int32),
                                        target_reduction=float(np.clip(ratio, 0.0, 0.99)))
    return trimesh.Trimesh(v, f, process=False)


class Hunyuan2Runner:
    def __init__(self, shape="dit-v2-0", paint="hunyuan3d-paint-v2-0", flashvdm=False, steps=None,
                 octree=384, max_faces=40000, num_chunks=8000, texture_size=2048, render_size=2048,
                 remove_floaters=True, use_rembg=False, seed=1234, decimator="pymeshlab", shape_dtype="fp16"):
        from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
        self.timer_load = StageTimer()
        repo, sub, dsteps, _ = SHAPE_MODELS[shape]
        self.cfg = dict(shape=shape, paint=paint, flashvdm=flashvdm, steps=steps or dsteps, octree=octree,
                        max_faces=max_faces, num_chunks=num_chunks, texture_size=texture_size,
                        render_size=render_size, remove_floaters=remove_floaters, seed=seed, decimator=decimator,
                        shape_dtype=shape_dtype)
        dt = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}[shape_dtype]
        if shape_dtype == "bf16":
            # o marching cubes do hy3dgen faz grid_logit.cpu().numpy(), e o NumPy nao tem bfloat16
            from hy3dgen.shapegen.models.autoencoders import surface_extractors as SE
            if not getattr(SE.MCSurfaceExtractor.run, "_cerise_patch", False):
                _orig = SE.MCSurfaceExtractor.run

                def _run(self_, grid_logit, **kw):
                    return _orig(self_, grid_logit.float(), **kw)
                _run._cerise_patch = True
                SE.MCSurfaceExtractor.run = _run
        with self.timer_load("load_shape"):
            self.shape = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
                repo, subfolder=sub, use_safetensors=(shape != "dit-v2-1"), device="cuda", dtype=dt)  # 2.1: .ckpt
            if flashvdm:
                self.shape.enable_flashvdm(topk_mode="merge")
            if shape_dtype != "fp16":
                self.shape.to(dtype=dt)  # converte tambem o VAE turbo carregado pelo FlashVDM
        self.paint = None
        if paint:
            from hy3dgen.texgen import Hunyuan3DPaintPipeline
            with self.timer_load("load_paint"):
                self.paint = Hunyuan3DPaintPipeline.from_pretrained("tencent/Hunyuan3D-2", subfolder=paint)
                self.paint.config.texture_size = texture_size
                self.paint.config.render_size = render_size
                from hy3dgen.texgen.differentiable_renderer.mesh_render import MeshRender
                self.paint.render = MeshRender(default_resolution=render_size, texture_size=texture_size)
        self.rembg = None
        if use_rembg:
            from hy3dgen.rembg import BackgroundRemover
            self.rembg = BackgroundRemover()
        from hy3dgen.shapegen import FaceReducer, FloaterRemover, DegenerateFaceRemover
        self.face_reducer, self.floater, self.degen = FaceReducer(), FloaterRemover(), DegenerateFaceRemover()

    # ------------------------------------------------------------------ textura instrumentada
    def _paint(self, mesh, image, T: StageTimer):
        from hy3dgen.texgen.utils.uv_warp_utils import mesh_uv_wrap
        p = self.paint
        with T("tex_delight"):
            img = p.recenter_image(image)
            img = p.models["delight_model"](img)
        with T("tex_uv_unwrap"):
            mesh = mesh_uv_wrap(mesh)
        with T("tex_render_cond"):
            p.render.load_mesh(mesh)
            elevs, azims, weights = (p.config.candidate_camera_elevs, p.config.candidate_camera_azims,
                                     p.config.candidate_view_weights)
            normal_maps = p.render_normal_multiview(elevs, azims, use_abs_coor=True)
            position_maps = p.render_position_multiview(elevs, azims)
            camera_info = [(((azim // 30) + 9) % 12) // {-20: 1, 0: 1, 20: 1, -90: 3, 90: 3}[elev] +
                           {-20: 0, 0: 12, 20: 24, -90: 36, 90: 40}[elev] for azim, elev in zip(azims, elevs)]
        with T("tex_multiview_diffusion"):
            mv = p.models["multiview_model"]([img], normal_maps + position_maps, camera_info)
        with T("tex_bake"):
            mv = [m.resize((p.config.render_size, p.config.render_size)) for m in mv]
            texture, mask = p.bake_from_multiview(mv, elevs, azims, weights, method=p.config.merge_method)
        with T("tex_inpaint"):
            mask_np = (mask.squeeze(-1).cpu().numpy() * 255).astype(np.uint8)
            texture = p.texture_inpaint(texture, mask_np)
        with T("tex_export"):
            p.render.set_texture(texture)
            out = p.render.save_mesh()
        return out

    # ------------------------------------------------------------------ geracao
    @torch.no_grad()
    def generate(self, image_path, out_glb, T: StageTimer | None = None):
        T = T or StageTimer()
        c = self.cfg
        with T("preprocess"):
            image = Image.open(image_path)
            if image.mode != "RGBA" and self.rembg is not None:
                image = self.rembg(image.convert("RGB"))
            image = image.convert("RGBA")
        with T("shape_diffusion"):
            latents = self.shape(image=image, num_inference_steps=c["steps"], octree_resolution=c["octree"],
                                 num_chunks=c["num_chunks"], generator=torch.manual_seed(c["seed"]),
                                 output_type="latent", enable_pbar=False)
        with T("shape_decode_mc"):
            mesh = self.shape._export(latents, output_type="trimesh", box_v=1.01, mc_level=0.0,
                                      num_chunks=c["num_chunks"], octree_resolution=c["octree"],
                                      mc_algo="mc", enable_pbar=False)[0]
        faces_raw = int(len(mesh.faces))
        with T("mesh_postproc"):
            if c["remove_floaters"]:
                mesh = self.floater(mesh)
                mesh = self.degen(mesh)
            if c["max_faces"] and c["decimator"] == "pymeshlab":
                mesh = self.face_reducer(mesh, max_facenum=c["max_faces"])
            elif c["max_faces"] and len(mesh.faces) > c["max_faces"]:
                mesh = fast_decimate(mesh, c["max_faces"], keep_largest=not c["remove_floaters"])
        if self.paint is not None:
            mesh = self._paint(mesh, image, T)
        with T("export_glb"):
            os.makedirs(os.path.dirname(os.path.abspath(out_glb)), exist_ok=True)
            mesh.export(out_glb)
        return dict(faces_raw=faces_raw, times=T.t)

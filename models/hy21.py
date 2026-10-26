"""Executor do Hunyuan3D-2.1: forma (hunyuan3d-dit-v2-1 via hy3dgen) + textura PBR (hy3dpaint 2.1: albedo +
metalico/rugosidade), instrumentado por etapa.

Adaptacoes para aarch64 (documentadas no relatorio):
  * o repositorio converte OBJ->GLB com o Blender (`bpy`), que nao tem wheel para Linux aarch64; aqui o GLB PBR e
    escrito com trimesh (baseColorTexture + metallicRoughnessTexture), e um modulo `bpy` vazio e injetado so para
    satisfazer o import do modulo mesh_utils;
  * o custom_rasterizer do 2.1 e compilado no proprio diretorio (build_ext --inplace) e entra na frente do sys.path,
    para nao conflitar com o do 2.0 instalado no site-packages;
  * para respeitar o teto de 24 GB, a forma e descarregada para a CPU durante a etapa de textura.
"""
from __future__ import annotations

import copy
import os
import sys
import types

import numpy as np
import torch
from PIL import Image

TP = os.environ.get("TP", "/workspace/third_party")
H21 = os.path.join(TP, "Hunyuan3D-2.1")
for p in (os.path.join(H21, "hy3dpaint"), os.path.join(H21, "hy3dpaint", "custom_rasterizer")):
    if p not in sys.path:
        sys.path.insert(0, p)
sys.modules.setdefault("bpy", types.ModuleType("bpy"))

from common import StageTimer  # noqa: E402
from hy2 import Hunyuan2Runner  # noqa: E402


def write_pbr_glb(obj_path, out_glb):
    """OBJ + texturas salvas pelo MeshRender 2.1 -> GLB com material PBR (sem Blender)."""
    import trimesh
    base = os.path.splitext(obj_path)[0]
    m = trimesh.load(obj_path, process=False, force="mesh")
    alb = Image.open(base + ".jpg") if os.path.exists(base + ".jpg") else Image.open(base + ".png")
    mr = None
    met_p, rough_p = base + "_metallic.jpg", base + "_roughness.jpg"
    if os.path.exists(met_p) and os.path.exists(rough_p):
        met = np.asarray(Image.open(met_p).convert("L"))
        rough = np.asarray(Image.open(rough_p).convert("L"))
        # glTF: canal G = rugosidade, B = metalico
        mr = Image.fromarray(np.stack([np.zeros_like(met), rough, met], -1).astype(np.uint8))
    mat = trimesh.visual.material.PBRMaterial(baseColorTexture=alb.convert("RGB"), metallicRoughnessTexture=mr,
                                              metallicFactor=1.0 if mr is not None else 0.0, roughnessFactor=1.0)
    m.visual = trimesh.visual.TextureVisuals(uv=m.visual.uv, material=mat)
    m.export(out_glb)
    return m


class Hunyuan21Runner:
    def __init__(self, steps=50, octree=384, max_faces=40000, num_chunks=8000, max_num_view=6, resolution=512,
                 use_super=True, offload_shape=True, seed=1234):
        self.timer_load = StageTimer()
        self.cfg = dict(steps=steps, octree=octree, max_faces=max_faces, max_num_view=max_num_view,
                        resolution=resolution, use_super=use_super, offload_shape=offload_shape)
        self.shape = Hunyuan2Runner(shape="dit-v2-1", paint=None, steps=steps, octree=octree, max_faces=max_faces,
                                    num_chunks=num_chunks, seed=seed)
        self.timer_load.t.update(self.shape.timer_load.t)
        try:
            from utils.torchvision_fix import apply_fix
            apply_fix()
        except Exception as e:  # noqa: BLE001
            print("aviso torchvision_fix:", e)
        cwd = os.getcwd()
        os.chdir(H21)  # o config usa caminhos relativos a raiz do repo
        try:
            from textureGenPipeline import Hunyuan3DPaintConfig, Hunyuan3DPaintPipeline
            conf = Hunyuan3DPaintConfig(max_num_view, resolution)
            conf.multiview_cfg_path = os.path.join(H21, "hy3dpaint/cfgs/hunyuan-paint-pbr.yaml")
            conf.realesrgan_ckpt_path = os.environ.get("REALESRGAN_CKPT", "/workspace/weights/RealESRGAN_x4plus.pth")
            if offload_shape:
                self.shape.shape.to("cpu"); torch.cuda.empty_cache()
            with self.timer_load("load_paint_pbr"):
                self.paint = Hunyuan3DPaintPipeline(conf)
            if offload_shape:
                self.paint_to("cpu")
        finally:
            os.chdir(cwd)

    def paint_to(self, dev):
        mv = self.paint.models["multiview_model"]
        mv.pipeline.to(dev)
        if hasattr(mv, "dino_v2"):
            mv.dino_v2.to(dev)
        sm = self.paint.models["super_model"].upsampler
        sm.model.to(dev); sm.device = torch.device(dev)
        torch.cuda.empty_cache()

    @torch.no_grad()
    def generate(self, image_path, out_glb, T: StageTimer | None = None):
        T = T or StageTimer()
        c = self.cfg
        odir = os.path.dirname(os.path.abspath(out_glb))
        os.makedirs(odir, exist_ok=True)
        if c["offload_shape"]:
            with T("offload_swap"):
                self.shape.shape.to("cuda")
        white = os.path.join(odir, "white_mesh.glb")
        info = self.shape.generate(image_path, white, T)
        p, vp = self.paint, self.paint.view_processor
        if c["offload_shape"]:
            with T("offload_swap"):
                self.shape.shape.to("cpu"); torch.cuda.empty_cache()
                self.paint_to("cuda")
        image = Image.open(image_path)
        with T("tex_uv_unwrap"):
            import trimesh
            from utils.uvwrap_utils import mesh_uv_wrap
            mesh = trimesh.load(white, force="mesh")
            mesh = mesh_uv_wrap(mesh)
        with T("tex_render_cond"):
            p.render.load_mesh(mesh=mesh)
            elevs, azims, weights = vp.bake_view_selection(p.config.candidate_camera_elevs,
                                                           p.config.candidate_camera_azims,
                                                           p.config.candidate_view_weights,
                                                           p.config.max_selected_view_num)
            normal_maps = vp.render_normal_multiview(elevs, azims, use_abs_coor=True)
            position_maps = vp.render_position_multiview(elevs, azims)
            im = image.resize((512, 512))
            if im.mode == "RGBA":
                bg = Image.new("RGB", im.size, (255, 255, 255)); bg.paste(im, mask=im.getchannel("A")); im = bg
            im = im.convert("RGB")
        with T("tex_multiview_diffusion_pbr"):
            mv = p.models["multiview_model"]([im], normal_maps + position_maps, prompt="high quality",
                                             custom_view_size=p.config.resolution, resize_input=True)
        with T("tex_super_resolution"):
            enh = {"albedo": copy.deepcopy(mv["albedo"]), "mr": copy.deepcopy(mv["mr"])}
            if c["use_super"]:
                for i in range(len(enh["albedo"])):
                    enh["albedo"][i] = p.models["super_model"](enh["albedo"][i])
                    enh["mr"][i] = p.models["super_model"](enh["mr"][i])
        with T("tex_bake"):
            rs = p.config.render_size
            enh["albedo"] = [x.resize((rs, rs)) for x in enh["albedo"]]
            enh["mr"] = [x.resize((rs, rs)) for x in enh["mr"]]
            tex, mask = vp.bake_from_multiview(enh["albedo"], elevs, azims, weights)
            tex_mr, mask_mr = vp.bake_from_multiview(enh["mr"], elevs, azims, weights)
        with T("tex_inpaint"):
            tex = vp.texture_inpaint(tex, (mask.squeeze(-1).cpu().numpy() * 255).astype(np.uint8))
            p.render.set_texture(tex, force_set=True)
            tex_mr = vp.texture_inpaint(tex_mr, (mask_mr.squeeze(-1).cpu().numpy() * 255).astype(np.uint8))
            p.render.set_texture_mr(tex_mr)
        with T("export_glb"):
            obj = os.path.join(odir, "textured.obj")
            p.render.save_mesh(obj, downsample=True)
            write_pbr_glb(obj, out_glb)
        if c["offload_shape"]:
            with T("offload_swap"):
                self.paint_to("cpu")
        return dict(faces_raw=info["faces_raw"], times=T.t)

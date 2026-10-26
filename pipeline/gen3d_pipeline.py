"""CERISE 2026 - pipeline imagem -> objeto 3D texturizado (GLB) para o app de RA.

Uso (no container cerise26_gen3d:latest):
    from gen3d_pipeline import Gen3DPipeline
    pipe = Gen3DPipeline()                       # carga quente unica (modelos ficam na GPU)
    out = pipe.generate("foto.jpg", "/tmp/saida", preset="padrao")
    # out = {"glb_path", "thumb_path", "stats": {"times": {...}, "faces", "size_bytes", ...}}

Modelo: familia Hunyuan3D-2 (forma: DiT com FlashVDM; textura: Hunyuan3D-Paint v2-0 turbo + delight),
escolhida no benchmark A1 (ver RELATORIO_SECAO.md). Presets medidos no A3: "rapido", "padrao", "alto".
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
import time

import numpy as np
import torch
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
HY2_ROOT = os.environ.get("HY2_ROOT", "/workspace/third_party/Hunyuan3D-2")
if HY2_ROOT not in sys.path:
    sys.path.insert(0, HY2_ROOT)
os.environ.setdefault("HY3DGEN_MODELS", "/workspace/hy3dgen_models")

import postprocess as PP  # noqa: E402

PRESETS_PATH = os.path.join(HERE, "presets.json")
DEFAULT_PRESETS = json.load(open(PRESETS_PATH)) if os.path.exists(PRESETS_PATH) else {}

SHAPE_MODELS = {
    "dit-v2-0": ("tencent/Hunyuan3D-2", "hunyuan3d-dit-v2-0"),
    "dit-v2-0-turbo": ("tencent/Hunyuan3D-2", "hunyuan3d-dit-v2-0-turbo"),
    "dit-v2-mini-turbo": ("tencent/Hunyuan3D-2mini", "hunyuan3d-dit-v2-mini-turbo"),
}


def fast_cleanup_decimate(mesh, max_faces, min_area_frac=0.01):
    """Pos-processamento rapido (A3): descarta componentes pequenos (< 1% da area do maior) e decima com
    fast-simplification (quadricas), em vez de FloaterRemover/DegenerateFaceRemover/FaceReducer (pymeshlab)."""
    import fast_simplification
    import trimesh
    comps = mesh.split(only_watertight=False)
    if len(comps) > 1:
        areas = np.array([c.area for c in comps])
        mesh = trimesh.util.concatenate([c for c, a in zip(comps, areas) if a >= min_area_frac * areas.max()])
    if len(mesh.faces) > max_faces:
        v, f = fast_simplification.simplify(np.asarray(mesh.vertices, np.float32), np.asarray(mesh.faces, np.int32),
                                            target_reduction=float(np.clip(1 - max_faces / len(mesh.faces), 0, 0.99)))
        mesh = trimesh.Trimesh(v, f, process=False)
    return mesh


class _Timer:
    def __init__(self):
        self.t = {}

    @contextlib.contextmanager
    def __call__(self, name):
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        try:
            yield
        finally:
            torch.cuda.synchronize()
            self.t[name] = round(self.t.get(name, 0.0) + time.perf_counter() - t0, 4)


class Gen3DPipeline:
    def __init__(self, presets: dict | None = None, gpu_cap_gb: float = 24.0, warmup: bool = True,
                 compress_method: str = "none"):
        # compress_method="none" e o padrao OBRIGATORIO para o app: o <model-viewer> embutido (offline) e o
        # ViroReact nao tem decodificadores Draco/meshopt/KTX2. O tamanho e controlado por decimacao + textura
        # JPEG reduzida. "draco"/"meshopt" ficam disponiveis apenas para comparacao (benchmark A3).
        from hy3dgen.rembg import BackgroundRemover
        from hy3dgen.shapegen import DegenerateFaceRemover, FaceReducer, FloaterRemover
        from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
        from hy3dgen.texgen import Hunyuan3DPaintPipeline
        t0 = time.perf_counter()
        total = torch.cuda.get_device_properties(0).total_memory
        torch.cuda.set_per_process_memory_fraction(min(1.0, gpu_cap_gb * 2 ** 30 / total), 0)
        self.presets = presets or DEFAULT_PRESETS
        self.compress_method = compress_method
        self.shapes, self.paints = {}, {}
        for p in self.presets.values():
            key = (p["shape"], bool(p.get("flashvdm", True)))
            if key not in self.shapes:
                repo, sub = SHAPE_MODELS[p["shape"]]
                pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(repo, subfolder=sub, use_safetensors=True,
                                                                        device="cuda")
                if key[1]:
                    pipe.enable_flashvdm(topk_mode="merge")
                self.shapes[key] = pipe
            if p["paint"] not in self.paints:
                paint = Hunyuan3DPaintPipeline.from_pretrained("tencent/Hunyuan3D-2", subfolder=p["paint"])
                if self.paints:  # o modelo de "delight" e o mesmo nos dois paints: compartilha (~2 GB a menos)
                    first = next(iter(self.paints.values()))
                    paint.models["delight_model"] = first.models["delight_model"]
                    import gc
                    gc.collect()
                    torch.cuda.empty_cache()
                self.paints[p["paint"]] = paint
        self.rembg = BackgroundRemover()
        self.face_reducer, self.floater, self.degen = FaceReducer(), FloaterRemover(), DegenerateFaceRemover()
        self.load_s = time.perf_counter() - t0
        self.mem_after_load_gb = torch.cuda.memory_allocated() / 2 ** 30
        self.warmup_s = None
        if warmup:
            sample = os.path.join(HERE, "assets", "warmup.png")
            if os.path.exists(sample):
                t1 = time.perf_counter()
                import tempfile
                with tempfile.TemporaryDirectory() as td:
                    for name in self.presets:
                        self.generate(sample, td, preset=name, thumbnail=False)
                self.warmup_s = time.perf_counter() - t1

    # --------------------------------------------------------------------------------------- textura
    @staticmethod
    def _paint(p, mesh, image, T, texture_size):
        from hy3dgen.texgen.differentiable_renderer.mesh_render import MeshRender
        from hy3dgen.texgen.utils.uv_warp_utils import mesh_uv_wrap
        if getattr(p, "_cerise_tex", p.config.texture_size) != texture_size:
            p.config.texture_size = p.config.render_size = texture_size
            p.render = MeshRender(default_resolution=texture_size, texture_size=texture_size)
        p._cerise_tex = texture_size
        with T("tex_delight"):
            img = p.models["delight_model"](p.recenter_image(image))
        with T("tex_uv_unwrap"):
            mesh = mesh_uv_wrap(mesh)
        with T("tex_render_cond"):
            p.render.load_mesh(mesh)
            el, az, w = (p.config.candidate_camera_elevs, p.config.candidate_camera_azims,
                         p.config.candidate_view_weights)
            nm = p.render_normal_multiview(el, az, use_abs_coor=True)
            pm = p.render_position_multiview(el, az)
            cam = [(((a // 30) + 9) % 12) // {-20: 1, 0: 1, 20: 1, -90: 3, 90: 3}[e] +
                   {-20: 0, 0: 12, 20: 24, -90: 36, 90: 40}[e] for a, e in zip(az, el)]
        with T("tex_multiview_diffusion"):
            mv = p.models["multiview_model"]([img], nm + pm, cam)
        with T("tex_bake"):
            mv = [m.resize((p.config.render_size, p.config.render_size)) for m in mv]
            tex, mask = p.bake_from_multiview(mv, el, az, w, method=p.config.merge_method)
        with T("tex_inpaint"):
            tex = p.texture_inpaint(tex, (mask.squeeze(-1).cpu().numpy() * 255).astype(np.uint8))
        with T("tex_export"):
            p.render.set_texture(tex)
            return p.render.save_mesh()

    # --------------------------------------------------------------------------------------- geracao
    @torch.no_grad()
    def generate(self, image_path: str, out_dir: str, preset: str = "padrao", thumbnail: bool = True,
                 seed: int = 1234) -> dict:
        if preset not in self.presets:
            raise ValueError(f"preset desconhecido: {preset} (opcoes: {list(self.presets)})")
        p = self.presets[preset]
        os.makedirs(out_dir, exist_ok=True)
        T = _Timer()
        torch.cuda.reset_peak_memory_stats()
        t_all = time.perf_counter()
        with T("bg_removal"):
            image = Image.open(image_path)
            alpha = np.asarray(image.convert("RGBA"))[..., 3] if image.mode in ("RGBA", "LA", "P") else None
            if alpha is None or alpha.min() > 250:  # sem transparencia util -> remove fundo
                image = self.rembg(image.convert("RGB"))
            image = image.convert("RGBA")
        shape = self.shapes[(p["shape"], bool(p.get("flashvdm", True)))]
        with T("shape_diffusion"):
            lat = shape(image=image, num_inference_steps=p["steps"], octree_resolution=p["octree"],
                        num_chunks=p.get("num_chunks", 20000), generator=torch.manual_seed(seed),
                        output_type="latent", enable_pbar=False)
        with T("shape_decode_mc"):
            mesh = shape._export(lat, output_type="trimesh", box_v=1.01, mc_level=0.0,
                                 num_chunks=p.get("num_chunks", 20000), octree_resolution=p["octree"],
                                 mc_algo="mc", enable_pbar=False)[0]
        faces_raw = int(len(mesh.faces))
        with T("mesh_postproc"):
            if p.get("fast_post", False):
                mesh = fast_cleanup_decimate(mesh, p["max_faces"])
            else:
                mesh = self.floater(mesh)
                mesh = self.degen(mesh)
                mesh = self.face_reducer(mesh, max_facenum=p["max_faces"])
        mesh = self._paint(self.paints[p["paint"]], mesh, image, T, p["texture_size"])
        raw = os.path.join(out_dir, "model_raw.glb")
        with T("export_glb"):
            mesh.export(raw)
        with T("mobile_postproc"):
            grounded = os.path.join(out_dir, "model_grounded.glb")
            geo = PP.ground_center_scale(raw, grounded, target_size_m=p.get("target_size_m", 0.30),
                                         front_yaw_deg=p.get("front_yaw_deg", 0.0))
            final = os.path.join(out_dir, "model.glb")
            PP.compress(grounded, final, method=self.compress_method, texture_size=p.get("mobile_texture", 1024))
        thumb = None
        if thumbnail:
            with T("thumbnail"):
                thumb = PP.thumbnail(grounded, os.path.join(out_dir, "thumb.png"))
        total = time.perf_counter() - t_all
        import trimesh
        sc = trimesh.load(final, force="scene", process=False) if self.compress_method == "none" else \
            trimesh.load(grounded, force="scene", process=False)
        faces = int(sum(len(g.faces) for g in sc.geometry.values()))
        ext_used = PP.extensions_used(final)
        stats = dict(preset=preset, params=p, times=T.t, total_s=round(total, 3), faces_raw=faces_raw, faces=faces,
                     size_bytes=os.path.getsize(final), size_raw_bytes=os.path.getsize(raw),
                     size_grounded_bytes=os.path.getsize(grounded), compress=self.compress_method,
                     gltf_extensions=ext_used,
                     geometry=geo, peak_gpu_gb=round(torch.cuda.max_memory_allocated() / 2 ** 30, 3))
        json.dump(stats, open(os.path.join(out_dir, "stats.json"), "w"), indent=1)
        return dict(glb_path=final, thumb_path=thumb, stats=stats)

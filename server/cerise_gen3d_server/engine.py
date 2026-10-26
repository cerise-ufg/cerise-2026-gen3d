"""Motor de geracao usado pelo worker.

`Engine` reaproveita os modelos carregados pelo `Gen3DPipeline` (pacote da frente de modelos, imagem
cerise26_gen3d:latest) e reimplementa o `generate` com:
  * callback de progresso por etapa (o app mostra estagio e porcentagem);
  * opcoes do contrato (texture=false -> so geometria; remove_background=false -> usa a imagem como esta);
  * "slots" concorrentes no MESMO processo, com pesos compartilhados: cada componente stateful (forma+FlashVDM,
    delight, multivista de cada paint, renderizador da miniatura) e protegido por uma trava propria e cada slot
    tem seu proprio MeshRender/config de textura. Assim dois jobs podem estar em etapas diferentes ao mesmo tempo
    (ex.: um na difusao de forma, outro na textura multivista ou em etapas de CPU) sem duplicar os ~11 GB de pesos.
  * sincronizacao por evento CUDA (nao `torch.cuda.synchronize()` global) nas medicoes por etapa.

`FakeEngine` simula o trabalho (sem GPU) para os testes automatizados da API/fila.
"""
from __future__ import annotations

import contextlib
import copy
import json
import os
import shutil
import sys
import threading
import time
from typing import Callable

PIPELINE_DIR = os.environ.get("GEN3D_PIPELINE_DIR", "/opt/gen3d/pipeline")

# rotulos em portugues mostrados no app
STAGE_LABELS = {
    "bg_removal": "removendo fundo",
    "shape_diffusion": "gerando geometria",
    "shape_decode_mc": "extraindo malha",
    "mesh_postproc": "otimizando malha",
    "tex_delight": "removendo iluminação",
    "tex_uv_unwrap": "planificando UV",
    "tex_render_cond": "renderizando vistas",
    "tex_multiview_diffusion": "texturizando (multivista)",
    "tex_bake": "projetando textura",
    "tex_inpaint": "preenchendo textura",
    "tex_export": "exportando textura",
    "export_glb": "exportando GLB",
    "mobile_postproc": "preparando para o celular",
    "thumbnail": "gerando miniatura",
}
STAGES = list(STAGE_LABELS)
TEX_STAGES = {s for s in STAGES if s.startswith("tex_")}

# tempo mediano por etapa (s) MEDIDO na rodada de presets do pipeline empacotado (READY.json, 19 objetos):
# usado so para converter "etapa atual" em porcentagem de progresso.
STAGE_MEDIANS = {
    "rapido": dict(bg_removal=0.028, shape_diffusion=3.641, shape_decode_mc=1.78, mesh_postproc=0.904,
                   tex_delight=4.212, tex_uv_unwrap=0.376, tex_render_cond=0.471, tex_multiview_diffusion=8.769,
                   tex_bake=0.86, tex_inpaint=0.276, tex_export=0.022, export_glb=0.215, mobile_postproc=0.919,
                   thumbnail=0.153),
    "padrao": dict(bg_removal=0.022, shape_diffusion=3.671, shape_decode_mc=3.182, mesh_postproc=2.218,
                   tex_delight=4.162, tex_uv_unwrap=1.023, tex_render_cond=0.685, tex_multiview_diffusion=8.797,
                   tex_bake=1.522, tex_inpaint=2.066, tex_export=0.074, export_glb=0.733, mobile_postproc=1.507,
                   thumbnail=0.333),
    "alto": dict(bg_removal=0.022, shape_diffusion=5.491, shape_decode_mc=4.624, mesh_postproc=1.99,
                 tex_delight=6.294, tex_uv_unwrap=2.545, tex_render_cond=0.924, tex_multiview_diffusion=51.886,
                 tex_bake=2.279, tex_inpaint=1.568, tex_export=0.073, export_glb=0.77, mobile_postproc=1.598,
                 thumbnail=0.348),
}


def progress_table(preset: str, texture: bool) -> dict[str, int]:
    med = STAGE_MEDIANS.get(preset, STAGE_MEDIANS["padrao"])
    stages = [s for s in STAGES if texture or s not in TEX_STAGES]
    total = sum(med[s] for s in stages) or 1.0
    out, acc = {}, 0.0
    for s in stages:
        out[s] = max(1, min(99, int(round(100 * acc / total))))
        acc += med[s]
    return out


ProgressCB = Callable[[str, int], None]


class _StageTimer:
    """Mede cada etapa (inclui a espera por travas) e avisa o callback de progresso no inicio da etapa."""

    def __init__(self, cb: ProgressCB | None, table: dict[str, int], cuda: bool):
        self.t: dict[str, float] = {}
        self.waits: dict[str, float] = {}
        self.cb, self.table, self.cuda = cb, table, cuda

    def _sync(self):
        if self.cuda:
            import torch
            ev = torch.cuda.Event()
            ev.record()
            ev.synchronize()

    @contextlib.contextmanager
    def __call__(self, name: str, lock: threading.Lock | None = None):
        if self.cb:
            try:
                self.cb(STAGE_LABELS.get(name, name), self.table.get(name, 50))
            except Exception:  # noqa: BLE001 - progresso nunca derruba o job
                pass
        t0 = time.perf_counter()
        if lock is not None:
            lock.acquire()
            self.waits[name] = round(self.waits.get(name, 0.0) + time.perf_counter() - t0, 4)
        try:
            yield
            self._sync()
        finally:
            if lock is not None:
                lock.release()
            self.t[name] = round(self.t.get(name, 0.0) + time.perf_counter() - t0, 4)


def compress_mobile(PP, glb_in: str, glb_out: str, texture_size: int = 1024, jpeg_quality: int = 85) -> int:
    """Prepara o GLB para o celular: textura reduzida (lado <= texture_size) e convertida para JPEG, SEM compressao
    de geometria (requisito do app: nada de Draco/meshopt/KTX2).

    O `postprocess.compress` da imagem cerise26_gen3d:latest chama `gltf-transform jpeg` sem `--formats`; na
    glTF-Transform 4.5 o padrao e `--formats jpeg` (so recomprime o que ja e JPEG) e a textura PNG passava intacta
    (constatado no teste ponta a ponta de 26/10: GLB do preset padrao com PNG 1024 de 2,4 MB). Aqui `--formats *`."""
    gt = os.path.join(PP.GLTF_TOOLS, "gltf-transform")
    tmp = glb_out + ".tmp.glb"
    shutil.copy(glb_in, tmp)
    try:
        PP._run([gt, "resize", tmp, tmp, "--width", str(texture_size), "--height", str(texture_size)])
        PP._run([gt, "jpeg", tmp, glb_out, "--formats", "*", "--quality", str(jpeg_quality)])
    finally:
        with contextlib.suppress(OSError):
            os.remove(tmp)
    return os.path.getsize(glb_out)


def glb_summary(path: str) -> dict:
    """Vertices/triangulos/materiais/texturas e extensoes do GLB final (mesmos campos que o mock do app)."""
    from pygltflib import GLTF2
    g = GLTF2().load(path)
    v = t = 0
    for m in g.meshes:
        for p in m.primitives:
            pos = g.accessors[p.attributes.POSITION] if p.attributes.POSITION is not None else None
            if pos is not None:
                v += pos.count
            if p.indices is not None:
                t += g.accessors[p.indices].count // 3
            elif pos is not None:
                t += pos.count // 3
    return dict(vertices=v, triangles=t, materials=len(g.materials), textures=len(g.textures),
                texture_mime=sorted({im.mimeType or "" for im in g.images}),
                gltf_extensions=list(g.extensionsUsed or []), glb_bytes=os.path.getsize(path))


class Engine:
    def __init__(self, presets: list[str], slots: int = 1, gpu_cap_gb: float = 24.0,
                 warmup_presets: list[str] | None = None, log=None):
        if PIPELINE_DIR not in sys.path:
            sys.path.insert(0, PIPELINE_DIR)
        import torch
        import gen3d_pipeline as G
        import postprocess as PP
        self.torch, self.G, self.PP = torch, G, PP
        self.log = log
        t0 = time.perf_counter()
        self.pipe = G.Gen3DPipeline(presets={k: G.DEFAULT_PRESETS[k] for k in presets}, gpu_cap_gb=gpu_cap_gb,
                                    warmup=False, compress_method="none")
        self.load_s = time.perf_counter() - t0
        self.presets = self.pipe.presets
        self.slots = max(1, int(slots))
        self.lock_shape = threading.Lock()
        self.lock_decode = threading.Lock()
        self.lock_delight = threading.Lock()
        self.lock_thumb = threading.Lock()
        self.lock_mv = {name: threading.Lock() for name in self.pipe.paints}
        self.slot_paints = [{name: (p if i == 0 else self._paint_view(p)) for name, p in self.pipe.paints.items()}
                            for i in range(self.slots)]
        self.gpu_name = torch.cuda.get_device_name(0)
        self.mem_after_load_gb = torch.cuda.memory_allocated() / 2 ** 30
        self.warmup_s = 0.0
        if warmup_presets:
            sample = os.path.join(PIPELINE_DIR, "assets", "warmup.png")
            import tempfile
            t1 = time.perf_counter()
            for name in warmup_presets:
                if name in self.presets and os.path.exists(sample):
                    with tempfile.TemporaryDirectory() as td:
                        self.generate(sample, td, name, slot=0)
            self.warmup_s = time.perf_counter() - t1
        self.release_cache()

    def release_cache(self):
        """Devolve ao sistema a memoria que o alocador do PyTorch guardou em cache (memoria unificada do Spark e
        compartilhada com a producao): chamado apos o aquecimento e quando o worker fica ocioso."""
        import gc
        gc.collect()
        self.torch.cuda.empty_cache()

    @staticmethod
    def _paint_view(p):
        """Copia rasa do Hunyuan3DPaintPipeline: compartilha os modelos (pesos), mas com config e
        renderizador proprios (o MeshRender guarda a malha/textura do job em andamento)."""
        from hy3dgen.texgen.differentiable_renderer.mesh_render import MeshRender
        v = copy.copy(p)
        v.config = copy.copy(p.config)
        v.render = MeshRender(default_resolution=p.config.render_size, texture_size=p.config.texture_size)
        v._cerise_tex = p.config.texture_size
        return v

    def gpu_memory(self) -> dict:
        t = self.torch
        return dict(allocated_gb=round(t.cuda.memory_allocated() / 2 ** 30, 3),
                    reserved_gb=round(t.cuda.memory_reserved() / 2 ** 30, 3),
                    peak_allocated_gb=round(t.cuda.max_memory_allocated() / 2 ** 30, 3),
                    peak_reserved_gb=round(t.cuda.max_memory_reserved() / 2 ** 30, 3))

    # ------------------------------------------------------------------------------------------- textura
    def _paint(self, v, mesh, image, T, texture_size, lock_mv):
        import numpy as np
        from hy3dgen.texgen.differentiable_renderer.mesh_render import MeshRender
        from hy3dgen.texgen.utils.uv_warp_utils import mesh_uv_wrap
        if getattr(v, "_cerise_tex", v.config.texture_size) != texture_size:
            v.config = copy.copy(v.config)
            v.config.texture_size = v.config.render_size = texture_size
            v.render = MeshRender(default_resolution=texture_size, texture_size=texture_size)
        v._cerise_tex = texture_size
        with T("tex_delight", self.lock_delight):
            img = v.models["delight_model"](v.recenter_image(image))
        with T("tex_uv_unwrap"):
            mesh = mesh_uv_wrap(mesh)
        with T("tex_render_cond"):
            v.render.load_mesh(mesh)
            el, az, w = (v.config.candidate_camera_elevs, v.config.candidate_camera_azims,
                         v.config.candidate_view_weights)
            nm = v.render_normal_multiview(el, az, use_abs_coor=True)
            pm = v.render_position_multiview(el, az)
            cam = [(((a // 30) + 9) % 12) // {-20: 1, 0: 1, 20: 1, -90: 3, 90: 3}[e] +
                   {-20: 0, 0: 12, 20: 24, -90: 36, 90: 40}[e] for a, e in zip(az, el)]
        with T("tex_multiview_diffusion", lock_mv):
            mv = v.models["multiview_model"]([img], nm + pm, cam)
        with T("tex_bake"):
            mv = [m.resize((v.config.render_size, v.config.render_size)) for m in mv]
            tex, mask = v.bake_from_multiview(mv, el, az, w, method=v.config.merge_method)
        with T("tex_inpaint"):
            tex = v.texture_inpaint(tex, (mask.squeeze(-1).cpu().numpy() * 255).astype(np.uint8))
        with T("tex_export"):
            v.render.set_texture(tex)
            return v.render.save_mesh()

    # ------------------------------------------------------------------------------------------- geracao
    def generate(self, image_path: str, out_dir: str, preset: str, texture: bool = True,
                 remove_background: bool = True, progress: ProgressCB | None = None, slot: int = 0,
                 seed: int = 1234) -> dict:
        import numpy as np
        import trimesh
        from PIL import Image
        torch, G, PP = self.torch, self.G, self.PP
        if preset not in self.presets:
            raise ValueError(f"preset nao carregado neste worker: {preset}")
        p = self.presets[preset]
        os.makedirs(out_dir, exist_ok=True)
        T = _StageTimer(progress, progress_table(preset, texture), cuda=True)
        single = self.slots == 1
        if single:
            torch.cuda.reset_peak_memory_stats()
        t_all = time.perf_counter()
        with torch.no_grad():
            with T("bg_removal"):
                image = Image.open(image_path)
                alpha = np.asarray(image.convert("RGBA"))[..., 3] if image.mode in ("RGBA", "LA", "P") else None
                if remove_background and (alpha is None or alpha.min() > 250):
                    image = self.pipe.rembg(image.convert("RGB"))
                image = image.convert("RGBA")
            shape = self.pipe.shapes[(p["shape"], bool(p.get("flashvdm", True)))]
            gen = torch.Generator(device="cpu").manual_seed(seed)  # gerador proprio: nao disputa o global
            # difusao (DiT + scheduler, com estado) e decodificacao (VAE + FlashVDM, que troca o processador de
            # atencao do decoder a cada chamada) usam componentes diferentes: uma trava para cada
            with T("shape_diffusion", self.lock_shape):
                lat = shape(image=image, num_inference_steps=p["steps"], octree_resolution=p["octree"],
                            num_chunks=p.get("num_chunks", 20000), generator=gen, output_type="latent",
                            enable_pbar=False)
            with T("shape_decode_mc", self.lock_decode):
                mesh = shape._export(lat, output_type="trimesh", box_v=1.01, mc_level=0.0,
                                     num_chunks=p.get("num_chunks", 20000), octree_resolution=p["octree"],
                                     mc_algo="mc", enable_pbar=False)[0]
            faces_raw = int(len(mesh.faces))
            with T("mesh_postproc"):
                if p.get("fast_post", False):
                    mesh = G.fast_cleanup_decimate(mesh, p["max_faces"])
                else:
                    mesh = self.pipe.floater(mesh)
                    mesh = self.pipe.degen(mesh)
                    mesh = self.pipe.face_reducer(mesh, max_facenum=p["max_faces"])
            raw = os.path.join(out_dir, "model_raw.glb")
            if texture:
                v = self.slot_paints[slot][p["paint"]]
                mesh = self._paint(v, mesh, image, T, p["texture_size"], self.lock_mv[p["paint"]])
                with T("export_glb"):
                    mesh.export(raw)
            else:
                with T("export_glb"):
                    mesh = trimesh.Trimesh(mesh.vertices, mesh.faces, process=False)
                    mesh.visual = trimesh.visual.ColorVisuals(mesh, vertex_colors=np.tile(
                        np.array([[190, 190, 190, 255]], np.uint8), (len(mesh.vertices), 1)))
                    mesh.export(raw)
            final = os.path.join(out_dir, "model.glb")
            with T("mobile_postproc"):
                grounded = os.path.join(out_dir, "model_grounded.glb")
                geo = PP.ground_center_scale(raw, grounded, target_size_m=p.get("target_size_m", 0.30),
                                             front_yaw_deg=p.get("front_yaw_deg", 0.0))
                if texture:
                    compress_mobile(PP, grounded, final, texture_size=p.get("mobile_texture", 1024))
                else:
                    shutil.copy(grounded, final)
            thumb = os.path.join(out_dir, "thumbnail.png")
            with T("thumbnail", self.lock_thumb):
                PP.thumbnail(grounded, thumb)
        total = time.perf_counter() - t_all
        for f in (raw, grounded):
            with contextlib.suppress(OSError):
                os.remove(f)
        summ = glb_summary(final)
        stats = dict(preset=preset, texture=bool(texture), remove_background=bool(remove_background),
                     seconds=round(total, 2), total_s=round(total, 3), times=T.t, lock_waits=T.waits,
                     faces_raw=faces_raw, faces=summ["triangles"], dims_m=geo.get("dims_m"),
                     peak_gpu_gb=round(torch.cuda.max_memory_allocated() / 2 ** 30, 3),
                     peak_gpu_scope="job" if single else "processo", slot=slot, **summ,
                     params={k: p[k] for k in ("shape", "paint", "steps", "octree", "max_faces", "texture_size",
                                               "mobile_texture", "target_size_m") if k in p})
        with open(os.path.join(out_dir, "stats.json"), "w") as f:
            json.dump(stats, f, indent=1)
        return dict(glb_path=final, thumb_path=thumb, stats=stats)


class FakeEngine:
    """Sem GPU: dorme `seconds` passando pelas etapas e devolve um GLB pequeno (cubo) + miniatura.
    Usado nos testes automatizados da API/fila e para ensaiar a operacao (start/stop/restart)."""

    def __init__(self, presets: list[str], slots: int = 1, seconds: float = 1.0, **_):
        self.presets = {k: {} for k in presets}
        self.slots = max(1, int(slots))
        self.seconds = seconds
        self.gpu_name = "fake"
        self.load_s = 0.0
        self.warmup_s = 0.0
        self.mem_after_load_gb = 0.0
        self.fail_marker = "FAIL"

    def gpu_memory(self) -> dict:
        return dict(allocated_gb=0.0, reserved_gb=0.0, peak_allocated_gb=0.0, peak_reserved_gb=0.0)

    def release_cache(self):
        pass

    def generate(self, image_path, out_dir, preset, texture=True, remove_background=True, progress=None,
                 slot=0, seed=1234) -> dict:
        import numpy as np
        import trimesh
        from PIL import Image
        os.makedirs(out_dir, exist_ok=True)
        table = progress_table(preset, texture)
        stages = list(table)
        mult = {"rapido": 1.0, "padrao": 1.3, "alto": 3.0}.get(preset, 1.0)
        t0 = time.perf_counter()
        for s in stages:
            if progress:
                progress(STAGE_LABELS[s], table[s])
            time.sleep(self.seconds * mult / len(stages))
        im = Image.open(image_path)
        if im.width == 77 and im.height == 77:  # imagem "veneno" usada nos testes de erro
            raise RuntimeError("falha simulada no motor (teste)")
        m = trimesh.creation.box(extents=(0.3, 0.2, 0.1))
        m.visual = trimesh.visual.ColorVisuals(m, vertex_colors=np.tile(np.array([[200, 80, 80, 255]], np.uint8),
                                                                           (len(m.vertices), 1)))
        glb = os.path.join(out_dir, "model.glb")
        m.export(glb)
        thumb = os.path.join(out_dir, "thumbnail.png")
        im.convert("RGB").resize((128, 128)).save(thumb)
        stats = dict(preset=preset, texture=bool(texture), seconds=round(time.perf_counter() - t0, 3),
                     total_s=round(time.perf_counter() - t0, 3), fake=True, slot=slot, **glb_summary(glb))
        return dict(glb_path=glb, thumb_path=thumb, stats=stats)

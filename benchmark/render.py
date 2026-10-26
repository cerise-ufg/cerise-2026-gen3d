"""Renderizador simples (nvdiffrast, contexto CUDA) para malhas texturizadas / com cor por vertice.

Usado para: (1) gerar as imagens de entrada a partir das malhas de referencia do GSO;
(2) renderizar os resultados de cada modelo (CLIP, grade qualitativa).
Convencao: Y para cima; camera orbita em torno de Y; azimute 0 = camera em +Z olhando para a origem.
"""
from __future__ import annotations

import math
import numpy as np
import torch
import trimesh
from PIL import Image

_GLCTX = None


def glctx():
    global _GLCTX
    if _GLCTX is None:
        import nvdiffrast.torch as dr
        _GLCTX = dr.RasterizeCudaContext()
    return _GLCTX


# ----------------------------------------------------------------------------- carga de malhas
class Part:
    """Uma geometria com aparencia: textura (uv+imagem), cor por vertice ou cor constante."""

    def __init__(self, v, f, uv=None, tex=None, vcol=None, const=(0.7, 0.7, 0.7)):
        self.v = np.asarray(v, np.float32)
        self.f = np.asarray(f, np.int32)
        self.uv = None if uv is None else np.asarray(uv, np.float32)
        self.tex = tex  # np.float32 HxWx3 em [0,1]
        self.vcol = None if vcol is None else np.asarray(vcol, np.float32)
        self.const = np.asarray(const, np.float32)


def _material_image_and_factor(mat):
    img, fac = None, None
    if mat is None:
        return None, None
    for attr in ("baseColorTexture", "image"):
        im = getattr(mat, attr, None)
        if im is not None:
            img = im
            break
    for attr in ("baseColorFactor", "main_color", "diffuse"):
        c = getattr(mat, attr, None)
        if c is not None:
            fac = np.asarray(c, np.float32).reshape(-1)[:3]
            if fac.max() > 1.0:
                fac = fac / 255.0
            break
    return img, fac


def geometry_to_part(g: trimesh.Trimesh) -> Part:
    vis = g.visual
    if isinstance(vis, trimesh.visual.texture.TextureVisuals):
        img, fac = _material_image_and_factor(vis.material)
        if img is not None and vis.uv is not None and len(vis.uv) == len(g.vertices):
            tex = np.asarray(img.convert("RGB"), np.float32) / 255.0
            if fac is not None:
                tex = tex * fac[None, None, :]
            return Part(g.vertices, g.faces, uv=vis.uv, tex=tex)
        return Part(g.vertices, g.faces, const=fac if fac is not None else (0.7, 0.7, 0.7))
    if isinstance(vis, trimesh.visual.color.ColorVisuals):
        if vis.kind == "vertex":
            return Part(g.vertices, g.faces, vcol=np.asarray(vis.vertex_colors)[:, :3] / 255.0)
        if vis.kind == "face":
            # duplica vertices para cor por face
            fc = np.asarray(vis.face_colors)[:, :3] / 255.0
            v = g.vertices[g.faces].reshape(-1, 3)
            f = np.arange(len(v)).reshape(-1, 3)
            return Part(v, f, vcol=np.repeat(fc, 3, axis=0))
    return Part(g.vertices, g.faces)


def load_parts(path: str, zup_to_yup: bool = False) -> list[Part]:
    scene = trimesh.load(path, force="scene", process=False)
    parts = []
    for name, g in scene.geometry.items():
        if not isinstance(g, trimesh.Trimesh) or len(g.faces) == 0:
            continue
        # aplica a transformacao do grafo de cena
        nodes = scene.graph.geometry_nodes.get(name, [])
        tf = scene.graph[nodes[0]][0] if nodes else np.eye(4)
        g = g.copy()
        g.apply_transform(tf)
        parts.append(geometry_to_part(g))
    if zup_to_yup:
        R = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], np.float32)  # (x,y,z)->(x,z,-y)
        for p in parts:
            p.v = p.v @ R.T
    return parts


def parts_bounds(parts):
    allv = np.concatenate([p.v for p in parts], 0)
    return allv.min(0), allv.max(0)


def normalize_parts(parts, extent=1.0):
    """Centraliza pela caixa envolvente e escala para maior dimensao = extent. Retorna (centro, escala)."""
    lo, hi = parts_bounds(parts)
    c = (lo + hi) / 2
    s = extent / float((hi - lo).max())
    for p in parts:
        p.v = (p.v - c) * s
    return c, s


def transform_parts(parts, T):
    for p in parts:
        p.v = (np.c_[p.v, np.ones(len(p.v))] @ T.T)[:, :3].astype(np.float32)


# ----------------------------------------------------------------------------- camera
def look_at(eye, target=(0, 0, 0), up=(0, 1, 0)):
    eye, target, up = map(lambda a: np.asarray(a, np.float64), (eye, target, up))
    z = eye - target
    z /= np.linalg.norm(z)
    x = np.cross(up, z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    M = np.eye(4)
    M[0, :3], M[1, :3], M[2, :3] = x, y, z
    M[:3, 3] = -M[:3, :3] @ eye
    return M


def perspective(fovy_deg, aspect=1.0, n=0.05, f=50.0):
    t = math.tan(math.radians(fovy_deg) / 2)
    P = np.zeros((4, 4))
    P[0, 0] = 1 / (aspect * t)
    P[1, 1] = 1 / t
    P[2, 2] = -(f + n) / (f - n)
    P[2, 3] = -2 * f * n / (f - n)
    P[3, 2] = -1
    return P


def orbit_eye(azim_deg, elev_deg, dist):
    a, e = math.radians(azim_deg), math.radians(elev_deg)
    return np.array([dist * math.cos(e) * math.sin(a), dist * math.sin(e), dist * math.cos(e) * math.cos(a)])


# ----------------------------------------------------------------------------- render
@torch.no_grad()
def render(parts, azim=0.0, elev=15.0, dist=2.2, fovy=30.0, res=512, ssaa=2, ambient=0.45,
           bg=(1.0, 1.0, 1.0), unlit=False):
    """Retorna PIL RGBA (fundo transparente) e PIL RGB (fundo bg)."""
    import nvdiffrast.torch as dr
    ctx = glctx()
    dev = "cuda"
    R = res * ssaa
    eye = orbit_eye(azim, elev, dist)
    V = look_at(eye)
    P = perspective(fovy)
    MVP = torch.tensor(P @ V, dtype=torch.float32, device=dev)
    light_dir = torch.tensor(eye / np.linalg.norm(eye) + np.array([0.3, 0.6, 0.2]), dtype=torch.float32, device=dev)
    light_dir = light_dir / light_dir.norm()

    color_acc = torch.zeros(R, R, 3, device=dev)
    alpha_acc = torch.zeros(R, R, 1, device=dev)
    depth_acc = torch.full((R, R, 1), 1e9, device=dev)
    for p in parts:
        v = torch.tensor(p.v, device=dev)
        f = torch.tensor(p.f, device=dev)
        vh = torch.cat([v, torch.ones_like(v[:, :1])], 1)
        clip = (vh @ MVP.T)[None]
        rast, _ = dr.rasterize(ctx, clip, f, resolution=[R, R])
        mask = (rast[..., 3:] > 0).float()[0]
        # normais por vertice
        tm = trimesh.Trimesh(p.v, p.f, process=False)
        vn = torch.tensor(np.asarray(tm.vertex_normals, np.float32), device=dev)
        n, _ = dr.interpolate(vn[None], rast, f)
        n = torch.nn.functional.normalize(n[0], dim=-1)
        if p.uv is not None and p.tex is not None:
            uv = torch.tensor(p.uv, device=dev)
            uvi, _ = dr.interpolate(uv[None], rast, f)
            uvi = uvi.clone()
            uvi[..., 1] = 1.0 - uvi[..., 1]
            tex = torch.tensor(p.tex, device=dev)[None].contiguous()
            albedo = dr.texture(tex, uvi.contiguous(), filter_mode="linear", boundary_mode="wrap")[0]
        elif p.vcol is not None:
            vc = torch.tensor(p.vcol, device=dev)
            albedo, _ = dr.interpolate(vc[None], rast, f)
            albedo = albedo[0]
        else:
            albedo = torch.tensor(p.const, device=dev).expand(R, R, 3)
        if unlit:
            shade = torch.ones(R, R, 1, device=dev)
        else:
            lam = (n * light_dir).sum(-1, keepdim=True).abs()  # abs: tolera normais invertidas
            shade = ambient + (1 - ambient) * lam
        col = (albedo * shade).clamp(0, 1)
        # profundidade em espaco de camera (z do rasterizador normalizado e suficiente p/ comparacao)
        z = rast[0, ..., 2:3]
        closer = (mask > 0) & (z < depth_acc)
        depth_acc = torch.where(closer, z, depth_acc)
        color_acc = torch.where(closer, col, color_acc)
        alpha_acc = torch.maximum(alpha_acc, mask)
    # opengl -> imagem (linha 0 no topo)
    color_acc = torch.flip(color_acc, [0])
    alpha_acc = torch.flip(alpha_acc, [0])
    rgba = torch.cat([color_acc, alpha_acc], -1).permute(2, 0, 1)[None]
    if ssaa > 1:
        # media premultiplicada
        prem = torch.cat([rgba[:, :3] * rgba[:, 3:], rgba[:, 3:]], 1)
        prem = torch.nn.functional.avg_pool2d(prem, ssaa)
        a = prem[:, 3:].clamp(min=1e-6)
        rgba = torch.cat([prem[:, :3] / a, prem[:, 3:]], 1)
    rgba = rgba[0].permute(1, 2, 0).clamp(0, 1).cpu().numpy()
    img_rgba = Image.fromarray((rgba * 255).round().astype(np.uint8), "RGBA")
    bgc = np.asarray(bg, np.float32)
    rgb = rgba[..., :3] * rgba[..., 3:] + bgc * (1 - rgba[..., 3:])
    img_rgb = Image.fromarray((rgb * 255).round().astype(np.uint8), "RGB")
    return img_rgba, img_rgb


def crop_to_content(rgba: Image.Image, out=1024, fill=0.85, bg=(255, 255, 255)):
    """Recorta pelo alfa, centraliza num quadrado (objeto ocupa `fill` do lado) e redimensiona.
    Retorna (RGBA, RGB sobre bg)."""
    a = np.asarray(rgba)[..., 3]
    ys, xs = np.nonzero(a > 8)
    if len(xs) == 0:
        im = rgba.resize((out, out))
    else:
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        crop = rgba.crop((x0, y0, x1, y1))
        side = int(max(x1 - x0, y1 - y0) / fill)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(crop, ((side - (x1 - x0)) // 2, (side - (y1 - y0)) // 2))
        im = canvas.resize((out, out), Image.LANCZOS)
    rgb = Image.new("RGB", im.size, bg)
    rgb.paste(im, mask=im.split()[3])
    return im, rgb


def appearance_kind(path):
    """'textura_uv', 'cor_vertice' ou 'nenhuma'."""
    try:
        scene = trimesh.load(path, force="scene", process=False)
    except Exception:
        return "erro"
    kind = "nenhuma"
    for g in scene.geometry.values():
        vis = getattr(g, "visual", None)
        if isinstance(vis, trimesh.visual.texture.TextureVisuals):
            img, _ = _material_image_and_factor(vis.material)
            if img is not None:
                return "textura_uv"
        if isinstance(vis, trimesh.visual.color.ColorVisuals) and vis.kind in ("vertex", "face"):
            kind = "cor_vertice"
    return kind


def has_texture(path):
    try:
        scene = trimesh.load(path, force="scene", process=False)
    except Exception:
        return False
    for g in scene.geometry.values():
        vis = getattr(g, "visual", None)
        if isinstance(vis, trimesh.visual.texture.TextureVisuals):
            img, _ = _material_image_and_factor(vis.material)
            if img is not None:
                return True
        if isinstance(vis, trimesh.visual.color.ColorVisuals) and vis.kind in ("vertex", "face"):
            return True
    return False

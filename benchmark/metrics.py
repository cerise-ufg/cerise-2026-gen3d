"""Metricas geometricas (Chamfer, F-score) com normalizacao + alinhamento ICP, e similaridade CLIP.

Definicoes (malhas normalizadas: centro da caixa envolvente na origem, maior dimensao = 1):
  - Chamfer (L2, nao quadratico): CD = media_{p in P} min_q ||p-q|| + media_{q in G} min_p ||q-p||
  - F-score@tau = 2*Prec*Rev/(Prec+Rev), Prec = fracao de P a menos de tau de G, Rev = fracao de G a menos de tau de P
Alinhamento: para cada rotacao inicial (12 guinadas em torno de Y x 2 convencoes de eixo), ICP ponto-a-ponto com
escala uniforme (Umeyama); fica a solucao de menor Chamfer.
"""
from __future__ import annotations

import numpy as np
import trimesh
from scipy.spatial import cKDTree


def load_mesh_points(path, n=50000, seed=0):
    scene = trimesh.load(path, force="scene", process=False)
    meshes = []
    for name, g in scene.geometry.items():
        if isinstance(g, trimesh.Trimesh) and len(g.faces):
            nodes = scene.graph.geometry_nodes.get(name, [])
            tf = scene.graph[nodes[0]][0] if nodes else np.eye(4)
            g = g.copy(); g.apply_transform(tf); meshes.append(g)
    m = trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]
    pts, _ = trimesh.sample.sample_surface(m, n, seed=seed)
    return np.asarray(pts, np.float64), m


def normalize_points(p):
    lo, hi = p.min(0), p.max(0)
    c = (lo + hi) / 2
    s = 1.0 / (hi - lo).max()
    T = np.eye(4); T[:3, :3] *= s; T[:3, 3] = -c * s
    return (p - c) * s, T


def rot_y(deg):
    a = np.radians(deg)
    R = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    return R


def umeyama(src, dst, with_scale=True):
    mu_s, mu_d = src.mean(0), dst.mean(0)
    xs, xd = src - mu_s, dst - mu_d
    cov = xd.T @ xs / len(src)
    U, D, Vt = np.linalg.svd(cov)
    S = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[2, 2] = -1
    R = U @ S @ Vt
    if with_scale:
        var_s = (xs ** 2).sum() / len(src)
        s = np.trace(np.diag(D) @ S) / var_s
    else:
        s = 1.0
    t = mu_d - s * R @ mu_s
    return s, R, t


def icp(src, dst, iters=40, with_scale=True, tree=None):
    tree = tree or cKDTree(dst)
    cur = src.copy()
    T = np.eye(4)
    for _ in range(iters):
        d, idx = tree.query(cur, k=1)
        # rejeita os 10% piores pares (robustez a pecas espurias)
        keep = d <= np.quantile(d, 0.9)
        s, R, t = umeyama(cur[keep], dst[idx[keep]], with_scale)
        s = float(np.clip(s, 0.7, 1.4))
        cur = s * cur @ R.T + t
        Ti = np.eye(4); Ti[:3, :3] = s * R; Ti[:3, 3] = t
        T = Ti @ T
    return cur, T


def chamfer_fscore(pred, gt, taus=(0.05, 0.1)):
    tp, tg = cKDTree(pred), cKDTree(gt)
    d_pg, _ = tg.query(pred, k=1)
    d_gp, _ = tp.query(gt, k=1)
    out = {"chamfer": float(d_pg.mean() + d_gp.mean())}
    for t in taus:
        p = float((d_pg < t).mean()); r = float((d_gp < t).mean())
        out[f"fscore@{t}"] = 0.0 if p + r == 0 else 2 * p * r / (p + r)
    return out


# convencoes de eixo testadas como inicializacao (identidade; Z-up -> Y-up)
CONVENTIONS = {
    "id": np.eye(3),
    "zup": np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float),
}


def align_and_score(pred_pts, gt_pts, n_icp=6000, seed=0):
    """pred_pts: pontos do resultado (qualquer escala). gt_pts: pontos GT ja normalizados.
    Retorna (metricas, T 4x4 que leva o resultado ORIGINAL para o referencial GT normalizado)."""
    rng = np.random.default_rng(seed)
    pn, Tn = normalize_points(pred_pts)
    sub_p = pn[rng.choice(len(pn), min(n_icp, len(pn)), replace=False)]
    sub_g = gt_pts[rng.choice(len(gt_pts), min(n_icp, len(gt_pts)), replace=False)]
    tree = cKDTree(sub_g)
    best = None
    for cname, C in CONVENTIONS.items():
        for yaw in range(0, 360, 30):
            R0 = rot_y(yaw) @ C
            rot = sub_p @ R0.T
            c0 = (rot.min(0) + rot.max(0)) / 2
            s0 = 1.0 / (rot.max(0) - rot.min(0)).max()  # renormaliza a caixa ja no referencial girado
            init = (rot - c0) * s0
            cur, Ticp = icp(init, sub_g, iters=30, tree=tree)
            d, _ = tree.query(cur, k=1)
            d2, _ = cKDTree(cur).query(sub_g, k=1)
            cd = d.mean() + d2.mean()
            if best is None or cd < best[0]:
                T0 = np.eye(4); T0[:3, :3] = R0
                Tc = np.eye(4); Tc[:3, :3] *= s0; Tc[:3, 3] = -c0 * s0
                best = (cd, Ticp @ Tc @ T0 @ Tn, cname, yaw)
    T = best[1]
    pa = (np.c_[pred_pts, np.ones(len(pred_pts))] @ T.T)[:, :3]
    m = chamfer_fscore(pa, gt_pts)
    m.update(dict(conv=best[2], yaw=best[3]))
    return m, T


class ClipScorer:
    def __init__(self, name="openai/clip-vit-large-patch14", device="cuda"):
        import torch
        from transformers import CLIPModel, CLIPProcessor
        self.torch = torch
        self.model = CLIPModel.from_pretrained(name, torch_dtype=torch.float16).to(device).eval()
        self.proc = CLIPProcessor.from_pretrained(name)
        self.device = device

    def embed(self, images):
        with self.torch.no_grad():
            x = self.proc(images=images, return_tensors="pt")["pixel_values"].to(self.device, self.torch.float16)
            e = self.model.get_image_features(pixel_values=x)
            return self.torch.nn.functional.normalize(e.float(), dim=-1)

    def sim(self, a, b):
        ea, eb = self.embed([a]), self.embed([b])
        return float((ea * eb).sum())

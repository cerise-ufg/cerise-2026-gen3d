"""Prepara o conjunto de avaliacao a partir do Google Scanned Objects (CC-BY 4.0).

Para cada objeto: carrega a malha de referencia (OBJ texturizado, Z para cima), converte para Y para cima,
normaliza (centro da caixa envolvente, maior dimensao = 1), renderiza a vista de entrada (1024 px, RGBA,
fundo transparente; azimute 0, elevacao 15 graus) e vistas de referencia (4 azimutes, 512 px), e amostra
pontos da superficie para as metricas geometricas.
"""
import argparse
import json
import os
import sys

import numpy as np
import trimesh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R  # noqa: E402

INPUT_AZ, INPUT_EL, DIST, FOV = 30.0, 15.0, 2.6, 30.0
VIEW_AZ = [30, 120, 210, 300]  # vista de entrada + 3 vistas novas (passo de 90 graus)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gso", default="/workspace/data/gso")
    ap.add_argument("--out", default="/workspace/data/eval")
    ap.add_argument("--npts", type=int, default=50000)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    index = []
    for name in sorted(os.listdir(a.gso)):
        obj = os.path.join(a.gso, name, "meshes", "model.obj")
        if not os.path.exists(obj):
            continue
        od = os.path.join(a.out, name)
        os.makedirs(od, exist_ok=True)
        parts = R.load_parts(obj, zup_to_yup=True)
        lo, hi = R.parts_bounds(parts)
        c, s = R.normalize_parts(parts, 1.0)
        rgba, _ = R.render(parts, azim=INPUT_AZ, elev=INPUT_EL, dist=DIST, fovy=FOV, res=1536)
        rgba, rgb = R.crop_to_content(rgba, out=1024, fill=0.85)
        rgba.save(os.path.join(od, "input.png"))
        rgb.save(os.path.join(od, "input_white.png"))
        for az in VIEW_AZ:
            im, _ = R.render(parts, azim=az, elev=INPUT_EL, dist=DIST, fovy=FOV, res=768)
            _, im = R.crop_to_content(im, out=512, fill=0.85)
            im.save(os.path.join(od, f"gt_view_az{az:03d}.png"))
        # malha normalizada (so geometria) + pontos de superficie
        allv = np.concatenate([p.v for p in parts]); off = 0; fs = []
        for p in parts:
            fs.append(p.f + off); off += len(p.v)
        gt = trimesh.Trimesh(allv, np.concatenate(fs), process=False)
        gt.export(os.path.join(od, "gt_norm.ply"))
        pts, _ = trimesh.sample.sample_surface(gt, a.npts, seed=0)
        np.save(os.path.join(od, "gt_points.npy"), pts.astype(np.float32))
        info = dict(name=name, faces=int(len(gt.faces)), vertices=int(len(gt.vertices)),
                    size_original_m=[float(x) for x in (hi - lo)], scale=float(s))
        json.dump(info, open(os.path.join(od, "info.json"), "w"), indent=1)
        index.append(info)
        print(name, info["faces"], "faces; dims (m, Y-up):", np.round(hi - lo, 3))
    json.dump(index, open(os.path.join(a.out, "index.json"), "w"), indent=1)


if __name__ == "__main__":
    main()

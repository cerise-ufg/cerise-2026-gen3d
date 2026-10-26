"""Avalia os resultados de uma ou mais configuracoes: alinhamento + Chamfer/F-score, renders e CLIP.

python evaluate.py --tags hy2_full,triposr  (le /workspace/results/bench/<tag>/<obj>/output.glb)
Gera: <tag>/<obj>/metrics.json, renders render_azXXX.png e <tag>/metrics.csv
"""
import argparse
import csv
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import metrics as M  # noqa: E402
import render as R  # noqa: E402
from prepare_gso import DIST, FOV, INPUT_AZ, INPUT_EL, VIEW_AZ  # noqa: E402


def evaluate_tag(tag, a, clip):
    tdir = os.path.join(a.results, tag)
    rows = []
    for o in sorted(os.listdir(a.data)):
        gdir = os.path.join(a.data, o)
        if not os.path.isdir(gdir):
            continue
        odir = os.path.join(tdir, o)
        glb = os.path.join(odir, "output.glb")
        st_path = os.path.join(odir, "stats.json")
        st = json.load(open(st_path)) if os.path.exists(st_path) else {}
        row = dict(tag=tag, object=o, ok=bool(st.get("ok", False)) and os.path.exists(glb))
        for k in ("total_s", "faces", "vertices", "size_bytes", "peak_alloc_gb", "peak_reserved_gb"):
            row[k] = st.get(k)
        for k, v in (st.get("times") or {}).items():
            row[f"t_{k}"] = v
        if row["ok"]:
            if a.skip_existing and os.path.exists(os.path.join(odir, "metrics.json")):
                row.update(json.load(open(os.path.join(odir, "metrics.json"))))
                rows.append(row)
                continue
            gt = np.load(os.path.join(gdir, "gt_points.npy")).astype(np.float64)
            pts, _ = M.load_mesh_points(glb, n=50000)
            m, T = M.align_and_score(pts, gt)
            row.update(m)
            row["appearance"] = R.appearance_kind(glb)
            parts = R.load_parts(glb)
            R.transform_parts(parts, T)
            sims_novel = []
            for az in VIEW_AZ:
                im, _ = R.render(parts, azim=az, elev=INPUT_EL, dist=DIST, fovy=FOV, res=768)
                _, rgb = R.crop_to_content(im, out=512, fill=0.85)
                rgb.save(os.path.join(odir, f"render_az{az:03d}.png"))
                if az == INPUT_AZ:
                    row["clip_input"] = clip.sim(Image.open(os.path.join(gdir, "input_white.png")), rgb)
                else:
                    sims_novel.append(clip.sim(Image.open(os.path.join(gdir, f"gt_view_az{az:03d}.png")), rgb))
            row["clip_novel"] = float(np.mean(sims_novel))
            json.dump({k: row[k] for k in ("chamfer", "fscore@0.05", "fscore@0.1", "conv", "yaw", "appearance",
                                           "clip_input", "clip_novel")},
                      open(os.path.join(odir, "metrics.json"), "w"), indent=1)
        rows.append(row)
        print(tag, o, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()
                       if k in ("ok", "chamfer", "fscore@0.05", "fscore@0.1", "clip_input", "clip_novel", "total_s")},
              flush=True)
    keys = sorted({k for r in rows for k in r})
    with open(os.path.join(tdir, "metrics.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", required=True)
    ap.add_argument("--data", default="/workspace/data/eval")
    ap.add_argument("--results", default="/workspace/results/bench")
    ap.add_argument("--skip-existing", action="store_true")
    a = ap.parse_args()
    clip = M.ClipScorer()
    # referencia: GT renderizado vs entrada (teto pratico do CLIP com este renderizador)
    for tag in a.tags.split(","):
        evaluate_tag(tag, a, clip)


if __name__ == "__main__":
    main()

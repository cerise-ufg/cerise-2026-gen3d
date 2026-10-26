"""Metricas medias de cada modelo restritas a um subconjunto comum de objetos (comparacao justa com os modelos
medidos em poucos objetos)."""
import csv
import os
import sys

import numpy as np

root = sys.argv[1]
tags = sys.argv[2].split(",")
labels = sys.argv[3].split(";")
objs = sys.argv[4].split(",")
title = sys.argv[5] if len(sys.argv) > 5 else ""
print(f"**{title}**\n")
print("| Modelo | n | Chamfer ↓ | F@0,05 ↑ | F@0,1 ↑ | CLIP entrada ↑ | CLIP vistas novas ↑ | Tempo mediano (s) |")
print("|---|---|---|---|---|---|---|---|")
for t, lab in zip(tags, labels):
    p = os.path.join(root, t, "metrics.csv")
    if not os.path.exists(p):
        continue
    rows = [r for r in csv.DictReader(open(p)) if r["object"] in objs and r.get("ok") == "True"]
    if not rows:
        continue
    m = lambda k: np.mean([float(r[k]) for r in rows])
    tm = np.median([float(r["total_s"]) for r in rows])
    f = lambda x, d=3: f"{x:.{d}f}".replace(".", ",")
    print(f"| {lab} | {len(rows)} | {f(m('chamfer'))} | {f(m('fscore@0.05'))} | {f(m('fscore@0.1'))} | "
          f"{f(m('clip_input'))} | {f(m('clip_novel'))} | {f(tm, 1)} |")

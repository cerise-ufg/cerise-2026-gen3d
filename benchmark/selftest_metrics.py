"""Teste de sanidade das metricas: a propria malha GT, com rotacao/escala/translacao arbitrarias aplicadas,
deve dar Chamfer ~ ruido de amostragem e F-score ~ 1 apos normalizacao + ICP."""
import json
import os

import numpy as np
import trimesh

DATA = "/workspace/data/eval"
OUT = "/workspace/results/bench/gt_selftest"
rng = np.random.default_rng(0)
for o in sorted(os.listdir(DATA)):
    if not os.path.isdir(os.path.join(DATA, o)):
        continue
    m = trimesh.load(os.path.join(DATA, o, "gt_norm.ply"), process=False)
    yaw = rng.uniform(0, 360)
    R = trimesh.transformations.rotation_matrix(np.radians(yaw), [0, 1, 0])
    Z = np.eye(4); Z[:3, :3] = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])  # Y-up -> Z-up
    S = np.diag([2.3, 2.3, 2.3, 1.0]); Tt = trimesh.transformations.translation_matrix([0.3, -1.0, 0.7])
    m.apply_transform(Tt @ S @ Z @ R)
    od = os.path.join(OUT, o); os.makedirs(od, exist_ok=True)
    m.export(os.path.join(od, "output.glb"))
    json.dump(dict(object=o, ok=True, total_s=0.0, times={}, yaw_applied=yaw), open(os.path.join(od, "stats.json"), "w"))
print("ok")

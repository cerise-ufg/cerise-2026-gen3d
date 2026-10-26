import sys

import numpy as np
import trimesh

sys.path.insert(0, "/workspace/benchmark")
import metrics as M

for o in sys.argv[1:]:
    gt = np.load(f"/workspace/data/eval/{o}/gt_points.npy").astype(np.float64)
    m = trimesh.load(f"/workspace/data/eval/{o}/gt_norm.ply", process=False)
    p1, _ = trimesh.sample.sample_surface(m, 50000, seed=1)
    g = trimesh.load(f"/workspace/results/bench/gt_selftest/{o}/output.glb", force="scene", process=False)
    gm = list(g.geometry.values())[0]
    print(o, "area", round(m.area, 3), "faces ply", len(m.faces), "faces glb", len(gm.faces),
          "| piso (GT vs GT seed1):", {k: round(v, 4) for k, v in M.chamfer_fscore(p1, gt).items()})

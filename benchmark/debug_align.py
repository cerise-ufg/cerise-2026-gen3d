import json
import sys

import numpy as np

sys.path.insert(0, "/workspace/benchmark")
import metrics as M

o = sys.argv[1]
gt = np.load(f"/workspace/data/eval/{o}/gt_points.npy").astype(np.float64)
pts, _ = M.load_mesh_points(f"/workspace/results/bench/gt_selftest/{o}/output.glb")
st = json.load(open(f"/workspace/results/bench/gt_selftest/{o}/stats.json"))
m, T = M.align_and_score(pts, gt)
print("applied yaw", st["yaw_applied"], "->", m)
print("T scale", np.cbrt(np.linalg.det(T[:3, :3])))
pa = (np.c_[pts, np.ones(len(pts))] @ T.T)[:, :3]
print("bbox pred", pa.min(0).round(3), pa.max(0).round(3))
print("bbox gt  ", gt.min(0).round(3), gt.max(0).round(3))
# refinamento sem corte e sem limite de escala
cur, T2 = M.icp(pa, gt[::5], iters=50, with_scale=True)
print("refinado:", M.chamfer_fscore(cur, gt))

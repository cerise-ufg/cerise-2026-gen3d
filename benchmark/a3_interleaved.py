"""A3 intercalado: carrega o Hunyuan3D-2 Turbo UMA vez e, para cada objeto, roda todas as variantes de parametros
em sequencia (mesma condicao de carga da GPU/CPU compartilhada para todas as variantes daquele objeto).
Variantes que exigem outros pesos (paint completo, bf16, sem FlashVDM) ficam na fila sequencial (queue_a3.sh).

Saida: /workspace/results/a3i/<variante>/<obj>/{output.glb, stats.json} + summary.json (formato do evaluate.py).
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "models"))
sys.path.insert(0, HERE)

import torch  # noqa: E402

from common import StageTimer, apply_gpu_cap, dump_json, gpu_peak_gb, gpu_reset_peak, mesh_stats  # noqa: E402

VARIANTS = {
    "i_base": {},
    "i_fastpost": {"remove_floaters": False, "decimator": "fast"},
    "i_oct256": {"octree": 256},
    "i_faces20k": {"max_faces": 20000},
    "i_faces10k": {"max_faces": 10000},
    "i_tex1024": {"texture_size": 1024, "render_size": 1024},
    "i_steps10": {"steps": 10},
    "i_rapido": {"octree": 256, "max_faces": 10000, "remove_floaters": False, "decimator": "fast",
                 "texture_size": 1024, "render_size": 1024},
    "i_padrao": {"octree": 384, "max_faces": 20000, "remove_floaters": False, "decimator": "fast"},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--objects", required=True)
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--data", default="/workspace/data/eval")
    ap.add_argument("--out", default="/workspace/results/a3i")
    a = ap.parse_args()
    from hy2 import Hunyuan2Runner
    from hy3dgen.texgen.differentiable_renderer.mesh_render import MeshRender
    apply_gpu_cap()
    base = dict(shape="dit-v2-0-turbo", paint="hunyuan3d-paint-v2-0-turbo", flashvdm=True, steps=5, octree=384,
                num_chunks=20000)
    t0 = time.perf_counter()
    r = Hunyuan2Runner(**base)
    load_s = time.perf_counter() - t0
    base_cfg = dict(r.cfg)
    variants = a.variants.split(",")
    objs = a.objects.split(",")
    # aquecimento
    r.generate(os.path.join(a.data, objs[0], "input.png"), os.path.join(a.out, "_warmup.glb"))
    summ = {v: dict(tag=v, config="hy2_turbo", kind="hy2", kwargs=dict(base, **VARIANTS[v]), load_s=load_s,
                    objects={}, loadavg_start=os.getloadavg()) for v in variants}
    cur_tex = base_cfg["texture_size"]
    for o in objs:
        for v in variants:
            cfg = dict(base_cfg, **VARIANTS[v])
            r.cfg = cfg
            if cfg["texture_size"] != cur_tex:
                r.paint.config.texture_size = r.paint.config.render_size = cfg["texture_size"]
                r.paint.render = MeshRender(default_resolution=cfg["render_size"], texture_size=cfg["texture_size"])
                cur_tex = cfg["texture_size"]
            T = StageTimer()
            gpu_reset_peak()
            glb = os.path.join(a.out, v, o, "output.glb")
            t1 = time.perf_counter()
            info = r.generate(os.path.join(a.data, o, "input.png"), glb, T)
            rec = dict(object=o, ok=True, total_s=time.perf_counter() - t1, times=T.t, faces_raw=info["faces_raw"],
                       loadavg=os.getloadavg()[0])
            rec.update(mesh_stats(glb))
            pk = gpu_peak_gb()
            rec.update(peak_alloc_gb=pk[0], peak_reserved_gb=pk[1])
            dump_json(rec, os.path.join(a.out, v, o, "stats.json"))
            summ[v]["objects"][o] = rec
            print(f"[{v}] {o}: {rec['total_s']:.1f}s faces={rec['faces']} etapas="
                  f"{ {k: round(x, 2) for k, x in T.t.items()} }", flush=True)
    for v in variants:
        summ[v]["loadavg_end"] = os.getloadavg()
        dump_json(summ[v], os.path.join(a.out, v, "summary.json"))
    print("FIM", flush=True)


if __name__ == "__main__":
    main()

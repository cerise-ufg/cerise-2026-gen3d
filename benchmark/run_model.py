"""Roda um modelo (configuracao) sobre o conjunto de avaliacao e grava GLB + estatisticas por objeto.

Exemplo:
  python run_model.py --config hy2_full --out /workspace/results/bench
  python run_model.py --config hy2_turbo --override '{"octree": 256}' --tag hy2_turbo_oct256
"""
import argparse
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "models"))
sys.path.insert(0, HERE)

import torch  # noqa: E402

from common import StageTimer, apply_gpu_cap, dump_json, gpu_peak_gb, gpu_reset_peak, mesh_stats  # noqa: E402

CONFIGS = {
    # ---- familia Hunyuan3D-2
    # padrao oficial (50 passos, octree 384, paint v2-0 completo); num_chunks so muda o lote de consultas do
    # decodificador volumetrico (mesmo resultado) - o padrao 8000 fica medido em "hy2_full_chunks8k"
    "hy2_full": ("hy2", dict(shape="dit-v2-0", paint="hunyuan3d-paint-v2-0", flashvdm=False, steps=50, octree=384,
                             num_chunks=50000)),
    "hy2_full_chunks8k": ("hy2", dict(shape="dit-v2-0", paint="hunyuan3d-paint-v2-0", flashvdm=False, steps=50,
                                      octree=384, num_chunks=8000)),
    "hy2_turbo": ("hy2", dict(shape="dit-v2-0-turbo", paint="hunyuan3d-paint-v2-0-turbo", flashvdm=True, steps=5,
                              octree=384, num_chunks=20000)),
    "hy2mini_turbo": ("hy2", dict(shape="dit-v2-mini-turbo", paint="hunyuan3d-paint-v2-0-turbo", flashvdm=True,
                                  steps=5, octree=380, num_chunks=20000)),
    "hy2_shape": ("hy2", dict(shape="dit-v2-0", paint=None, steps=50, octree=384)),
    "hy21_shape": ("hy2", dict(shape="dit-v2-1", paint=None, steps=50, octree=384)),
    "hy21_full": ("hy21", dict()),
    # ---- outros
    "triposr": ("triposr", dict(mc_resolution=256)),
    "instantmesh": ("instantmesh", dict()),
    "trellis": ("trellis", dict()),
}


def build(kind, kw):
    if kind == "hy2":
        from hy2 import Hunyuan2Runner
        return Hunyuan2Runner(**kw)
    if kind == "hy21":
        from hy21 import Hunyuan21Runner
        return Hunyuan21Runner(**kw)
    if kind == "triposr":
        from triposr_runner import TripoSRRunner
        return TripoSRRunner(**kw)
    if kind == "instantmesh":
        from instantmesh_runner import InstantMeshRunner
        return InstantMeshRunner(**kw)
    if kind == "trellis":
        from trellis_runner import TrellisRunner
        return TrellisRunner(**kw)
    raise KeyError(kind)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--override", default="{}")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--data", default="/workspace/data/eval")
    ap.add_argument("--out", default="/workspace/results/bench")
    ap.add_argument("--objects", default="all", help="lista separada por virgula ou 'all'")
    ap.add_argument("--no-warmup", action="store_true")
    a = ap.parse_args()
    kind, kw = CONFIGS[a.config]
    kw = dict(kw, **json.loads(a.override))
    tag = a.tag or a.config
    outdir = os.path.join(a.out, tag)
    os.makedirs(outdir, exist_ok=True)
    frac = apply_gpu_cap()
    print(f"[{tag}] limite de memoria do alocador: {frac:.3f} da GPU", flush=True)

    objs = sorted(d for d in os.listdir(a.data) if os.path.isdir(os.path.join(a.data, d)))
    if a.objects != "all":
        objs = [o for o in objs if o in a.objects.split(",")]

    gpu_reset_peak()
    t0 = time.perf_counter()
    runner = build(kind, kw)
    load_s = time.perf_counter() - t0
    load_peak = gpu_peak_gb()
    print(f"[{tag}] carga do modelo: {load_s:.1f} s; memoria apos carga {torch.cuda.memory_allocated()/2**30:.2f} GB",
          flush=True)
    summary = dict(tag=tag, config=a.config, kind=kind, kwargs=kw, load_s=load_s, load_peak_gb=load_peak[0],
                   load_times=getattr(runner, "timer_load", StageTimer()).t, objects={},
                   loadavg_start=os.getloadavg(), started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    if not a.no_warmup and objs:
        T = StageTimer()
        t1 = time.perf_counter()
        try:
            runner.generate(os.path.join(a.data, objs[0], "input.png"), os.path.join(outdir, "_warmup.glb"), T)
            summary["warmup_s"] = time.perf_counter() - t1
            print(f"[{tag}] aquecimento: {summary['warmup_s']:.1f} s", flush=True)
        except Exception as e:
            traceback.print_exc()
            summary["warmup_error"] = repr(e)

    for o in objs:
        T = StageTimer()
        gpu_reset_peak()
        glb = os.path.join(outdir, o, "output.glb")
        rec = dict(object=o)
        t1 = time.perf_counter()
        try:
            info = runner.generate(os.path.join(a.data, o, "input.png"), glb, T)
            rec.update(ok=True, total_s=time.perf_counter() - t1, times=T.t, faces_raw=info.get("faces_raw"))
            rec.update(mesh_stats(glb))
        except Exception as e:
            traceback.print_exc()
            rec.update(ok=False, error=repr(e)[:500], total_s=time.perf_counter() - t1, times=T.t)
            torch.cuda.empty_cache()
        pk = gpu_peak_gb()
        rec.update(peak_alloc_gb=pk[0], peak_reserved_gb=pk[1])
        dump_json(rec, os.path.join(outdir, o, "stats.json"))
        summary["objects"][o] = rec
        print(f"[{tag}] {o}: ok={rec['ok']} {rec['total_s']:.1f}s faces={rec.get('faces')} "
              f"pico={pk[0]:.2f}GB etapas={ {k: round(v, 2) for k, v in T.t.items()} }", flush=True)
    summary["loadavg_end"] = os.getloadavg()
    dump_json(summary, os.path.join(outdir, "summary.json"))
    print(f"[{tag}] FIM (loadavg inicio {summary['loadavg_start'][0]:.1f}, fim {summary['loadavg_end'][0]:.1f})",
          flush=True)


if __name__ == "__main__":
    main()

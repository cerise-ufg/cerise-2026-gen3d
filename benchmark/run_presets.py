"""Mede os presets do pipeline empacotado (Gen3DPipeline) no conjunto GSO e nas fotos reais (CC0).

Grava, por preset, results/presets/preset_<nome>/<obj>/{model.glb, model_raw.glb, thumb.png, stats.json} e um
output.glb (= model_raw.glb, referencial do modelo) + stats.json no formato do evaluate.py.
"""
import argparse
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="/workspace/data/eval")
    ap.add_argument("--real", default="/workspace/data/real")
    ap.add_argument("--out", default="/workspace/results/presets")
    ap.add_argument("--presets", default=None)
    a = ap.parse_args()
    from gen3d_pipeline import DEFAULT_PRESETS, Gen3DPipeline
    names = a.presets.split(",") if a.presets else list(DEFAULT_PRESETS)
    t0 = time.perf_counter()
    pipe = Gen3DPipeline(presets={k: DEFAULT_PRESETS[k] for k in names}, warmup=True)
    info = dict(load_s=pipe.load_s, warmup_s=pipe.warmup_s, mem_after_load_gb=pipe.mem_after_load_gb,
                init_total_s=time.perf_counter() - t0, loadavg=os.getloadavg())
    print("carga", json.dumps(info), flush=True)
    jobs = [(o, os.path.join(a.data, o, "input.png")) for o in sorted(os.listdir(a.data))
            if os.path.isdir(os.path.join(a.data, o))]
    jobs += [(os.path.splitext(f)[0], os.path.join(a.real, f)) for f in sorted(os.listdir(a.real)) if f.endswith(".jpg")]
    for name in names:
        tag = f"preset_{name}"
        summ = dict(tag=tag, config=name, kind="pipeline", kwargs=DEFAULT_PRESETS[name], load_s=info["load_s"],
                    warmup_s=info["warmup_s"], objects={}, loadavg_start=os.getloadavg())
        for o, img in jobs:
            od = os.path.join(a.out, tag, o)
            try:
                r = pipe.generate(img, od, preset=name)
                st = r["stats"]
                shutil.copy(os.path.join(od, "model_raw.glb"), os.path.join(od, "output.glb"))
                rec = dict(object=o, ok=True, total_s=st["total_s"], times=st["times"], faces=st["faces"],
                           faces_raw=st["faces_raw"], size_bytes=st["size_bytes"], size_raw_bytes=st["size_raw_bytes"],
                           peak_alloc_gb=st["peak_gpu_gb"], real_photo=o.startswith("cc0_"))
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                rec = dict(object=o, ok=False, error=repr(e)[:400])
                os.makedirs(od, exist_ok=True)
            json.dump(rec, open(os.path.join(od, "stats.json"), "w"), indent=1)
            summ["objects"][o] = rec
            print(f"[{tag}] {o}: ok={rec['ok']} {rec.get('total_s', 0):.1f}s faces={rec.get('faces')} "
                  f"size={rec.get('size_bytes')} etapas={rec.get('times')}", flush=True)
        summ["loadavg_end"] = os.getloadavg()
        json.dump(summ, open(os.path.join(a.out, tag, "summary.json"), "w"), indent=1)
    info["presets"] = names
    json.dump(info, open(os.path.join(a.out, f"pipeline_load_{'_'.join(names)}.json"), "w"), indent=1)
    print("FIM", flush=True)


if __name__ == "__main__":
    main()

"""Resumo dos presets (a partir dos summary.json) em Markdown: tempos (GSO / fotos reais), faces, tamanho, memoria."""
import json
import os
import statistics as st
import sys

root = sys.argv[1]
names = sys.argv[2].split(",") if len(sys.argv) > 2 else ["rapido", "padrao", "alto"]
rows = []
for n in names:
    p = os.path.join(root, f"preset_{n}", "summary.json")
    if not os.path.exists(p):
        continue
    s = json.load(open(p))
    ok = [o for o in s["objects"].values() if o.get("ok")]
    gso = [o for o in ok if not o.get("real_photo")]
    real = [o for o in ok if o.get("real_photo")]

    def med(lst, k):
        v = [o[k] for o in lst if o.get(k) is not None]
        return st.median(v) if v else float("nan")

    def rng(lst, k):
        v = [o[k] for o in lst if o.get(k) is not None]
        return (min(v), max(v)) if v else (float("nan"), float("nan"))
    stages = {}
    for o in ok:
        for k, v in o["times"].items():
            stages.setdefault(k, []).append(v)
    rows.append(dict(preset=n, n_ok=len(ok), n=len(s["objects"]), t_gso=med(gso, "total_s"), t_real=med(real, "total_s"),
                     t_rng=rng(ok, "total_s"), faces=med(ok, "faces"), size_mb=med(ok, "size_bytes") / 1e6,
                     size_rng=tuple(x / 1e6 for x in rng(ok, "size_bytes")), peak=max(o.get("peak_alloc_gb", 0) for o in ok),
                     load_s=s.get("load_s"), warmup_s=s.get("warmup_s"),
                     stages={k: round(st.median(v), 2) for k, v in stages.items()}))
f = lambda x, d=1: f"{x:.{d}f}".replace(".", ",")
print("| Preset | OK | Tempo mediano GSO (s) | Tempo mediano fotos reais (s) | Faixa (s) | Faces (med.) | GLB final (MB, med.) | Faixa GLB (MB) | Pico GPU (GB) |")
print("|---|---|---|---|---|---|---|---|---|")
for r in rows:
    print(f"| {r['preset']} | {r['n_ok']}/{r['n']} | {f(r['t_gso'])} | {f(r['t_real'])} | {f(r['t_rng'][0])}–{f(r['t_rng'][1])} | "
          f"{r['faces']:.0f} | {f(r['size_mb'], 2)} | {f(r['size_rng'][0], 2)}–{f(r['size_rng'][1], 2)} | {f(r['peak'])} |")
print()
for r in rows:
    print(r["preset"], "etapas (mediana):", r["stages"], "carga:", r["load_s"], "aquec:", r["warmup_s"])

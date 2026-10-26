"""Tempos medianos por variante (summary.json) e razao em relacao a uma variante base, objeto a objeto."""
import json
import os
import statistics as st
import sys

root, tags, base = sys.argv[1], sys.argv[2].split(","), sys.argv[3]
S = {t: json.load(open(os.path.join(root, t, "summary.json"))) for t in tags if os.path.exists(os.path.join(root, t, "summary.json"))}
b = S[base]["objects"]
for t, s in S.items():
    ok = {o: r for o, r in s["objects"].items() if r.get("ok")}
    tot = [r["total_s"] for r in ok.values()]
    ratios = [r["total_s"] / b[o]["total_s"] for o, r in ok.items() if o in b and b[o].get("ok")]
    post = [r["times"].get("mesh_postproc", 0) for r in ok.values()]
    tex = [sum(v for k, v in r["times"].items() if k.startswith("tex_")) for r in ok.values()]
    shp = [r["times"].get("shape_diffusion", 0) + r["times"].get("shape_decode_mc", 0) for r in ok.values()]
    print(f"{t:14s} n={len(ok)} total_med={st.median(tot):6.1f}s razao_vs_base(med)={st.median(ratios):.2f} "
          f"forma={st.median(shp):5.1f} posproc={st.median(post):5.1f} textura={st.median(tex):5.1f} "
          f"faces={st.median([r.get('faces', 0) for r in ok.values()]):.0f} MB={st.median([r.get('size_bytes', 0) for r in ok.values()])/1e6:.2f}")

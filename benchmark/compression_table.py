"""A3 - tamanho do GLB final por estrategia de compressao (sobre os GLBs assentados do preset).
"none" (JPEG + decimacao) e o caminho USADO no app; Draco/meshopt sao variantes NAO usadas no app porque o
<model-viewer> embutido (offline) e o ViroReact nao tem os decodificadores.

python compression_table.py --root /workspace/results/presets/preset_padrao --out-json ... --out-png ...
"""
import argparse
import json
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import postprocess as PP  # noqa: E402

COMBOS = [("none", 2048), ("none", 1024), ("none", 512), ("draco", 1024), ("meshopt", 1024)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-png", required=True)
    a = ap.parse_args()
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for o in sorted(os.listdir(a.root)):
            g = os.path.join(a.root, o, "model_grounded.glb")
            if not os.path.exists(g):
                continue
            r = dict(object=o, grounded_bytes=os.path.getsize(g))
            for m, t in COMBOS:
                out = os.path.join(td, f"{o}_{m}_{t}.glb")
                r[f"{m}_{t}"] = PP.compress(g, out, method=m, texture_size=t)
                if m == "none":
                    r[f"{m}_{t}_ext"] = PP.extensions_used(out)["extensions"]
            rows.append(r)
            print(json.dumps(r))
    json.dump(rows, open(a.out_json, "w"), indent=1)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sys.path.insert(0, HERE)
    import aggregate as AG
    AG.style()
    labels = ["JPEG 2048\n(sem compr. geom.)", "JPEG 1024\n(USADO no app)", "JPEG 512", "Draco + JPEG 1024\n(não usado no app)",
              "meshopt + JPEG 1024\n(não usado no app)"]
    keys = [f"{m}_{t}" for m, t in COMBOS]
    med = [np.median([r[k] for r in rows]) / 1e6 for k in keys]
    mn = [np.min([r[k] for r in rows]) / 1e6 for k in keys]
    mx = [np.max([r[k] for r in rows]) / 1e6 for k in keys]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    cols = [AG.CAT[0], AG.CAT[0], AG.CAT[0], AG.MUTED, AG.MUTED]
    x = np.arange(len(keys))
    ax.bar(x, med, width=0.56, color=cols, edgecolor=AG.SURF, linewidth=2, zorder=3)
    ax.errorbar(x, med, yerr=[np.array(med) - mn, np.array(mx) - med], fmt="none", ecolor=AG.INK2, capsize=4, lw=1, zorder=4)
    for xi, v in zip(x, med):
        ax.annotate(f"{v:.2f} MB".replace(".", ","), (xi, v), xytext=(10, 4), textcoords="offset points",
                    ha="left", fontsize=9, color=AG.INK2)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_ylabel("tamanho do GLB final (MB) — mediana, barras = mín/máx")
    ax.grid(axis="x", visible=False)
    ax.set_title(f"A3 — tamanho do GLB por estratégia ({len(rows)} objetos, preset padrão, 20k faces)", loc="left",
                 fontsize=11.5, color=AG.INK)
    fig.tight_layout()
    fig.savefig(a.out_png, dpi=150)
    print(a.out_png)


if __name__ == "__main__":
    main()

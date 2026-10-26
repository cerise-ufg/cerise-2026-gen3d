"""A3: tabela + graficos das variantes de otimizacao (tempo por etapa e delta de qualidade vs. base)."""
import argparse
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aggregate as AG  # noqa: E402

A3_LABELS = {
    "a3_base": "base (turbo, oct 384, 40k faces, tex 2048)",
    "a3_fastpost": "pós-proc. rápido (sem pymeshlab)",
    "a3_oct256": "octree 256",
    "a3_faces20k": "20k faces",
    "a3_faces10k": "10k faces",
    "a3_tex1024": "textura 1024",
    "a3_paintfull": "paint completo (não-turbo)",
    "a3_steps10": "10 passos",
    "a3_bf16": "forma em bf16",
    "a3_noflashvdm": "sem FlashVDM",
    "hy2_full_sub": "Hunyuan3D-2.0 padrão oficial",
}


def plot_quality(S, base, out, title):
    AG.style()
    fig, axes = plt.subplots(1, 3, figsize=(13, 0.5 * len(S) + 1.8), sharey=True)
    y = np.arange(len(S))[::-1]
    for ax, key, lab in ((axes[0], "f005", "F-score@0,05 (média) ↑"), (axes[1], "chamfer", "Chamfer (média) ↓"),
                         (axes[2], "clip_in", "CLIP entrada (média) ↑")):
        vals = [s[key] for s in S]
        ax.axvline(base[key], color=AG.BASE, lw=1.2, ls="--", zorder=1)
        ax.scatter(vals, y, s=60, color=AG.CAT[0], edgecolor=AG.SURF, linewidth=2, zorder=3)
        for v, yi in zip(vals, y):
            ax.annotate(f"{v:.3f}".replace(".", ","), (v, yi), xytext=(6, -3), textcoords="offset points",
                        fontsize=8, color=AG.INK2)
        ax.set_xlabel(lab)
        ax.grid(axis="y", visible=False)
        lo, hi = np.nanmin(vals + [base[key]]), np.nanmax(vals + [base[key]])
        pad = (hi - lo) * 0.25 + 1e-3
        ax.set_xlim(lo - pad, hi + pad * 1.6)
    axes[0].set_yticks(y)
    axes[0].set_yticklabels([s["label"] for s in S])
    fig.suptitle(title + " (linha tracejada = base)", fontsize=12, color=AG.INK)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default=",".join(k for k in A3_LABELS if k != "hy2_full_sub"))
    ap.add_argument("--bench", default="/workspace/results/a3")
    ap.add_argument("--out", default="/workspace/evidencias")
    ap.add_argument("--resdir", default="/workspace/resultados")
    a = ap.parse_args()
    AG.LABELS.update(A3_LABELS)
    S = []
    for t in a.tags.split(","):
        try:
            S.append(AG.summarize(t, *AG.load(a.bench, t)))
        except FileNotFoundError as e:
            print("ignorado", t, e)
    AG.write_tables(S, "a3", a.resdir)
    base = [s for s in S if s["tag"] == "a3_base"][0]
    AG.plot_stages(S, os.path.join(a.out, "a3_tempo_por_etapa.png"),
                   "A3 — variantes do Hunyuan3D-2 Turbo (7 objetos GSO): tempo por etapa")
    plot_quality(S, base, os.path.join(a.out, "a3_qualidade_variantes.png"), "A3 — qualidade por variante")


if __name__ == "__main__":
    main()

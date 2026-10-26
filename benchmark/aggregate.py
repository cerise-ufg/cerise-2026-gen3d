"""Agrega os resultados (summary.json + metrics.csv de cada configuracao) em tabelas (CSV/Markdown) e graficos.

python aggregate.py --tags triposr,hy2mini_turbo,... --prefix a1 --out /workspace/evidencias --resdir /workspace/resultados
"""
import argparse
import csv
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# paleta categorica de referencia (ordem fixa) + tinta/superficie (skill dataviz, modo claro)
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURF, INK, INK2, MUTED, GRID, BASE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
MARKERS = ["o", "s", "D", "^", "v", "P", "X", "*"]

LABELS = {
    "triposr": "TripoSR",
    "hy2mini_turbo": "Hunyuan3D-2mini-Turbo",
    "hy2_turbo": "Hunyuan3D-2-Turbo",
    "hy2_full": "Hunyuan3D-2.0 (padrão)",
    "hy21_full": "Hunyuan3D-2.1 (PBR)",
    "hy21_shape": "Hunyuan3D-2.1 (só forma)",
    "instantmesh": "InstantMesh",
    "gt_selftest": "GT sem textura (ref.)",
}
STAGE_GROUPS = [
    ("Pré-processamento", ("preprocess", "bg_removal")),
    ("Rede generativa principal", ("shape_diffusion", "triplane_forward", "multiview_diffusion", "lrm_planes")),
    ("Decodificação + iso-superfície", ("shape_decode_mc", "mesh_extract_mc", "mesh_extract_flexicubes")),
    ("Pós-processamento da malha", ("mesh_postproc",)),
    ("Textura (multivista + bake)", ("tex_",)),
    ("Exportação / outros", ("export_glb", "offload_swap", "mobile_postproc", "thumbnail")),
]


def style():
    plt.rcParams.update({
        "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
        "axes.edgecolor": BASE, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
        "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
        "font.family": "DejaVu Sans", "legend.frameon": False,
    })


def group_of(stage):
    for g, keys in STAGE_GROUPS:
        if any(stage == k or (k.endswith("_") and stage.startswith(k)) for k in keys):
            return g
    return "Exportação / outros"


def load(resdir_bench, tag):
    s = json.load(open(os.path.join(resdir_bench, tag, "summary.json")))
    rows = list(csv.DictReader(open(os.path.join(resdir_bench, tag, "metrics.csv"))))
    return s, rows


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def summarize(tag, s, rows):
    ok = [r for r in rows if r.get("ok") == "True"]
    objs = s.get("objects", {})
    times = [o["total_s"] for o in objs.values() if o.get("ok")]
    stage = {}
    for o in objs.values():
        if not o.get("ok"):
            continue
        for k, v in (o.get("times") or {}).items():
            stage.setdefault(group_of(k), []).append(v)
    n_ok = len([o for o in objs.values() if o.get("ok")])
    grp = {g: float(np.sum(v) / max(n_ok, 1)) for g, v in stage.items()}
    app = sorted({r.get("appearance", "") for r in ok} - {""})
    return dict(
        tag=tag, label=LABELS.get(tag, tag), n=len(objs) or len(rows), n_ok=n_ok,
        t_median=float(np.median(times)) if times else np.nan, t_mean=float(np.mean(times)) if times else np.nan,
        t_min=float(np.min(times)) if times else np.nan,
        load_s=s.get("load_s"), warmup_s=s.get("warmup_s"),
        peak_gb=float(np.max([o.get("peak_alloc_gb", 0) for o in objs.values()])) if objs else np.nan,
        faces=float(np.median([f(r.get("faces")) for r in ok])) if ok else np.nan,
        size_mb=float(np.median([f(r.get("size_bytes")) for r in ok]) / 1e6) if ok else np.nan,
        chamfer=float(np.nanmean([f(r.get("chamfer")) for r in ok])) if ok else np.nan,
        f005=float(np.nanmean([f(r.get("fscore@0.05")) for r in ok])) if ok else np.nan,
        f01=float(np.nanmean([f(r.get("fscore@0.1")) for r in ok])) if ok else np.nan,
        clip_in=float(np.nanmean([f(r.get("clip_input")) for r in ok])) if ok else np.nan,
        clip_nov=float(np.nanmean([f(r.get("clip_novel")) for r in ok])) if ok else np.nan,
        appearance="/".join(app), stages=grp,
        loadavg=s.get("loadavg_start"),
    )


def write_tables(S, prefix, resdir):
    os.makedirs(resdir, exist_ok=True)
    keys = ["label", "tag", "appearance", "n_ok", "n", "t_median", "t_mean", "t_min", "load_s", "warmup_s", "peak_gb",
            "faces", "size_mb", "chamfer", "f005", "f01", "clip_in", "clip_nov"]
    with open(os.path.join(resdir, f"{prefix}_tabela.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys + ["stages"])
        w.writeheader()
        for s in S:
            w.writerow({**{k: s[k] for k in keys}, "stages": json.dumps(s["stages"], ensure_ascii=False)})
    hdr = ("| Modelo | Aparência | OK | Tempo mediano (s) | Carga (s) | Pico GPU (GB) | Faces (med.) | GLB (MB) | "
           "Chamfer ↓ | F@0,05 ↑ | F@0,1 ↑ | CLIP entrada ↑ | CLIP vistas novas ↑ |")
    lines = [hdr, "|" + "---|" * 13]

    def n(x, d=2):
        return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{d}f}".replace(".", ",")
    for s in S:
        lines.append(f"| {s['label']} | {s['appearance'] or '–'} | {s['n_ok']}/{s['n']} | {n(s['t_median'], 1)} | "
                     f"{n(s['load_s'], 0)} | {n(s['peak_gb'], 1)} | {n(s['faces'], 0)} | {n(s['size_mb'], 1)} | "
                     f"{n(s['chamfer'], 3)} | {n(s['f005'], 3)} | {n(s['f01'], 3)} | {n(s['clip_in'], 3)} | "
                     f"{n(s['clip_nov'], 3)} |")
    open(os.path.join(resdir, f"{prefix}_tabela.md"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


def plot_quality_vs_time(S, out, title):
    style()
    S = [s for s in S if not np.isnan(s["t_median"]) and s["t_median"] > 0]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    for ax, key, lab in ((axes[0], "f01", "F-score@0,1 (média) ↑"), (axes[1], "clip_in", "CLIP entrada × render (média) ↑")):
        for i, s in enumerate(S):
            ax.scatter(s["t_median"], s[key], s=70, color=CAT[i % 8], marker=MARKERS[i % 8], zorder=3,
                       edgecolor=SURF, linewidth=2, label=s["label"])
            ax.annotate(s["label"], (s["t_median"], s[key]), xytext=(6, 5), textcoords="offset points", fontsize=8.5,
                        color=INK2)
        ax.set_xscale("log")
        ax.set_xlabel("tempo mediano por objeto (s, escala log) — carga quente")
        ax.set_ylabel(lab)
        vals = [s[key] for s in S]
        pad = (max(vals) - min(vals)) * 0.12 + 1e-3
        ax.set_ylim(min(vals) - pad, max(vals) + pad)
        xs = [s["t_median"] for s in S]
        ax.set_xlim(min(xs) / 1.6, max(xs) * 3.5)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=min(6, len(l)), fontsize=8.5, bbox_to_anchor=(0.5, 0.0))
    fig.suptitle(title, fontsize=12, color=INK)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(out)


def plot_stages(S, out, title):
    style()
    groups = [g for g, _ in STAGE_GROUPS]
    S = [s for s in S if s["stages"]]
    fig, ax = plt.subplots(figsize=(11, 0.62 * len(S) + 1.6))
    y = np.arange(len(S))[::-1]
    left = np.zeros(len(S))
    for gi, g in enumerate(groups):
        vals = np.array([s["stages"].get(g, 0.0) for s in S])
        if vals.sum() == 0:
            continue
        ax.barh(y, vals, left=left, height=0.56, color=CAT[gi], edgecolor=SURF, linewidth=1.5, label=g, zorder=3)
        left += vals
    for yi, tot in zip(y, left):
        ax.text(tot, yi, f"  {tot:.1f} s", va="center", fontsize=9, color=INK2)
    ax.set_yticks(y)
    ax.set_yticklabels([s["label"] for s in S])
    ax.set_xlabel("tempo médio por objeto (s), por etapa")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, left.max() * 1.15)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3, fontsize=8.5)
    ax.set_title(title, fontsize=12, color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", required=True)
    ap.add_argument("--labels", default=None, help="rotulos (mesma ordem das tags), separados por ';'")
    ap.add_argument("--prefix", default="a1")
    ap.add_argument("--bench", default="/workspace/results/bench")
    ap.add_argument("--out", default="/workspace/evidencias")
    ap.add_argument("--resdir", default="/workspace/resultados")
    ap.add_argument("--title", default="Benchmark A1 — GSO (13 objetos), DGX Spark GB10")
    a = ap.parse_args()
    tags = a.tags.split(",")
    if a.labels:
        for t, l in zip(tags, a.labels.split(";")):
            LABELS[t] = l
    S = []
    for t in tags:
        try:
            S.append(summarize(t, *load(a.bench, t)))
        except FileNotFoundError as e:
            print("ignorado", t, e)
    write_tables(S, a.prefix, a.resdir)
    os.makedirs(a.out, exist_ok=True)
    plot_quality_vs_time([s for s in S if s["tag"] != "gt_selftest"], os.path.join(a.out, f"{a.prefix}_qualidade_vs_tempo.png"),
                         a.title + ": qualidade × tempo")
    plot_stages([s for s in S if s["tag"] != "gt_selftest"], os.path.join(a.out, f"{a.prefix}_tempo_por_etapa.png"),
                a.title + ": tempo por etapa")


if __name__ == "__main__":
    main()

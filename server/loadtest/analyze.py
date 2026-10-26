"""Analise dos testes de carga (A5): tabelas (CSV/Markdown) e graficos (matplotlib, 150 dpi, pt-BR).

Uso: python analyze.py <pasta_resultados_loadtest> <pasta_saida_tabelas> <pasta_evidencias>
"""
from __future__ import annotations

import csv
import glob
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

CONFIGS = [  # tag -> rotulo, cor
    ("sync_nolock", "2025: Flask síncrono, sem trava", "#c0392b"),
    ("sync_lock", "2025: Flask síncrono, com trava", "#e67e22"),
    ("q1_burst", "2026: fila + 1 worker", "#2471a3"),
    ("q2_burst", "2026: fila + 2 slots (pesos compartilhados)", "#17a589"),
]
LABEL = {t: l for t, l, _ in CONFIGS}
COLOR = {t: c for t, _, c in CONFIGS}


def pct(a, q):
    a = [x for x in a if x is not None]
    return float(np.percentile(a, q)) if a else float("nan")


def load(res_dir, tag):
    p = os.path.join(res_dir, f"{tag}.json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def gpu_peak(res_dir, tag):
    for name in (f"gpu_{tag}.csv", f"gpu_{tag.replace('sync_', 'sync_')}.csv"):
        p = os.path.join(res_dir, name)
        if os.path.exists(p):
            vals = []
            av = []
            with open(p) as f:
                for r in csv.DictReader(f):
                    try:
                        vals.append(float(r["used_mib"]) / 1024)
                        av.append(float(r["mem_available_gib"]))
                    except (ValueError, KeyError):
                        pass
            if vals:
                return max(vals), min(av)
    return float("nan"), float("nan")


def level_rows(d, tag):
    rows = []
    recs = d["records"]
    for lvl in sorted({r["level"] for r in recs}):
        rr = [r for r in recs if r["level"] == lvl]
        ok = [r for r in rr if r.get("ok")]
        lat = [r["latency_s"] for r in ok]
        qw = [(r.get("timings") or {}).get("queue_s") for r in ok] if rr[0]["mode"] == "queue" else []
        run = [(r.get("timings") or {}).get("run_s") for r in ok] if rr[0]["mode"] == "queue" else \
            [r.get("server_seconds") for r in ok]
        span = max(r["t_end"] for r in rr) - min(r["t_submit"] for r in rr)
        trocados = sum(1 for r in ok if r.get("arquivo_trocado"))
        rows.append(dict(config=tag, clientes=lvl, jobs=len(rr), ok=len(ok), erros=len(rr) - len(ok),
                         taxa_erro=round((len(rr) - len(ok)) / len(rr), 3),
                         lat_p50=round(pct(lat, 50), 1), lat_p95=round(pct(lat, 95), 1),
                         lat_p99=round(pct(lat, 99), 1), lat_max=round(max(lat), 1) if lat else float("nan"),
                         fila_p50=round(pct(qw, 50), 1) if qw else "", fila_p95=round(pct(qw, 95), 1) if qw else "",
                         exec_p50=round(pct(run, 50), 1) if run else "",
                         vazao_jobs_min=round(len(ok) / span * 60, 2) if span > 0 else float("nan"),
                         duracao_nivel_s=round(span, 1), respostas_trocadas=trocados,
                         erros_exemplo="; ".join(sorted({(r.get("error") or "")[:60] for r in rr if not r.get("ok")}))[:160]))
    return rows


def probe_rows(d, tag):
    t0 = min(r["t_submit"] for r in d["records"]) if d["records"] else 0
    t1 = max(r["t_end"] for r in d["records"]) if d["records"] else 0
    out = []
    for kind in sorted({p["kind"] for p in d["probes"]}):
        pp = [p for p in d["probes"] if p["kind"] == kind and t0 <= p["t"] <= t1]
        ok = [p["latency_s"] * 1000 for p in pp if p["status"] == 200]
        bad = [p for p in pp if p["status"] != 200]
        if not pp:
            continue
        out.append(dict(config=tag, rota={"health": "GET /api/v1/health", "job": "GET /api/v1/jobs/{id}",
                                          "index": "GET / (Flask)"}[kind],
                        n=len(pp), p50_ms=round(pct(ok, 50), 1), p95_ms=round(pct(ok, 95), 1),
                        p99_ms=round(pct(ok, 99), 1), max_ms=round(max(ok), 1) if ok else float("nan"),
                        erros=len(bad), taxa_req_s=round(len(pp) / max(1e-9, t1 - t0), 1)))
    return out


def write_table(rows, path_csv, path_md, cols=None):
    if not rows:
        return
    cols = cols or list(rows[0])
    with open(path_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with open(path_md, "w", encoding="utf-8") as f:
        f.write("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n")
        for r in rows:
            f.write("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |\n")


def main(res_dir, tab_dir, ev_dir):
    os.makedirs(tab_dir, exist_ok=True)
    os.makedirs(ev_dir, exist_ok=True)
    plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": 0.3})
    data = {t: load(res_dir, t) for t, _, _ in CONFIGS}
    lv, pr = [], []
    for t, d in data.items():
        if d:
            lv += level_rows(d, t)
            pr += probe_rows(d, t)
    write_table(lv, os.path.join(tab_dir, "carga_niveis.csv"), os.path.join(tab_dir, "carga_niveis.md"))
    write_table(pr, os.path.join(tab_dir, "carga_api.csv"), os.path.join(tab_dir, "carga_api.md"))

    # resumo por configuracao (todas as rodadas do burst)
    resumo = []
    for t, d in data.items():
        if not d:
            continue
        recs = d["records"]
        ok = [r for r in recs if r.get("ok")]
        span = max(r["t_end"] for r in recs) - min(r["t_submit"] for r in recs)
        busy = sum((r["t_end"] - r["t_submit"]) for r in recs)
        g, av = gpu_peak(res_dir, t)
        l16 = [r for r in lv if r["config"] == t and r["clientes"] == max(x["clientes"] for x in lv if x["config"] == t)]
        resumo.append(dict(config=LABEL[t], jobs=len(recs), ok=len(ok), taxa_erro=round(1 - len(ok) / len(recs), 3),
                           lat_p50=round(pct([r["latency_s"] for r in ok], 50), 1),
                           lat_p95=round(pct([r["latency_s"] for r in ok], 95), 1),
                           lat_p99=round(pct([r["latency_s"] for r in ok], 99), 1),
                           vazao_16_jobs_min=l16[0]["vazao_jobs_min"] if l16 else "",
                           gpu_pico_gb=round(g, 1), mem_disp_min_gb=round(av, 1),
                           respostas_trocadas=sum(1 for r in ok if r.get("arquivo_trocado"))))
    write_table(resumo, os.path.join(tab_dir, "carga_resumo.csv"), os.path.join(tab_dir, "carga_resumo.md"))

    # ---------- grafico 1: latencia p50/p95, espera na fila, vazao e erros x clientes
    fig, axs = plt.subplots(2, 2, figsize=(12.5, 8.4))
    axs = axs.ravel()
    for t, _, _ in CONFIGS:
        rr = [r for r in lv if r["config"] == t]
        if not rr:
            continue
        x = [r["clientes"] for r in rr]
        axs[0].plot(x, [r["lat_p50"] for r in rr], "o-", color=COLOR[t], label=LABEL[t])
        axs[0].plot(x, [r["lat_p95"] for r in rr], "s--", color=COLOR[t], alpha=0.6)
        if any(r["fila_p50"] != "" for r in rr):
            axs[1].plot(x, [r["fila_p50"] for r in rr], "o-", color=COLOR[t], label=LABEL[t])
            axs[1].plot(x, [r["fila_p95"] for r in rr], "s--", color=COLOR[t], alpha=0.6)
        axs[2].plot(x, [r["vazao_jobs_min"] for r in rr], "o-", color=COLOR[t], label=LABEL[t])
        axs[3].plot(x, [100 * r["taxa_erro"] for r in rr], "o-", color=COLOR[t], label=LABEL[t])
    for ax in axs:
        ax.set_xscale("log", base=2)
        ax.set_xticks([1, 2, 4, 8, 16])
        ax.set_xticklabels(["1", "2", "4", "8", "16"])
        ax.set_xlabel("clientes simultâneos")
    axs[0].set_ylabel("latência ponta a ponta (s)")
    axs[0].set_title("Latência do job (linha cheia p50, tracejada p95)")
    axs[1].set_ylabel("espera na fila (s)")
    axs[1].set_title("Espera na fila — arquitetura 2026 (cheia p50, tracejada p95)")
    axs[2].set_ylabel("jobs concluídos por minuto")
    axs[2].set_title("Vazão")
    axs[3].set_ylabel("% de pedidos com erro")
    axs[3].set_title("Taxa de erro")
    axs[2].legend(fontsize=8, loc="best")
    fig.suptitle("Teste de carga — preset rápido, rajadas de N clientes (Spark GB10, produção ativa)", fontsize=11)
    fig.tight_layout()
    fig.savefig(os.path.join(ev_dir, "srv_carga_latencia_vazao_erros.png"), dpi=150)
    plt.close(fig)

    # ---------- grafico 2: responsividade da API durante a carga
    if pr:
        short = {"sync_nolock": "2025\nsem trava", "sync_lock": "2025\ncom trava", "q1_burst": "2026\n1 worker",
                 "q2_burst": "2026\n2 slots", "q1_probe": "2026, 1 worker\nsonda ~50 req/s"}
        rota_c = {"GET / (Flask)": "GET /", "GET /api/v1/health": "/health", "GET /api/v1/jobs/{id}": "/jobs/{id}"}
        rows_pl = list(pr)
        dpp = load(res_dir, "q1_probe")
        if dpp:
            rows_pl += probe_rows(dpp, "q1_probe")
        fig, ax = plt.subplots(figsize=(11, 4.6))
        labels, p50, p95, p99, cols = [], [], [], [], []
        for r in rows_pl:
            labels.append(f"{short.get(r['config'], r['config'])}\n{rota_c.get(r['rota'], r['rota'])}")
            p50.append(r["p50_ms"])
            p95.append(r["p95_ms"])
            p99.append(r["p99_ms"])
            cols.append(COLOR.get(r["config"], "#5b2c6f"))
        x = np.arange(len(labels))
        ax.bar(x - 0.25, p50, 0.25, color=cols, alpha=0.40)
        ax.bar(x, p95, 0.25, color=cols, alpha=0.70)
        ax.bar(x + 0.25, p99, 0.25, color=cols, alpha=1.0)
        for xi, v in zip(x, p95):
            ax.text(xi, v * 1.12, f"{v:.0f}", ha="center", fontsize=7)
        from matplotlib.patches import Patch
        ax.legend(handles=[Patch(color="#555", alpha=a, label=n) for a, n in ((0.4, "p50"), (0.7, "p95 (valor)"),
                                                                               (1.0, "p99"))], fontsize=8)
        ax.set_yscale("log")
        ax.set_ylabel("latência da requisição (ms, log)")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=7.5)
        ax.set_title("Responsividade da API com a GPU ocupada (sondas de leitura durante as rajadas)")
        fig.tight_layout()
        fig.savefig(os.path.join(ev_dir, "srv_carga_api_responsividade.png"), dpi=150)
        plt.close(fig)

    # ---------- grafico 3: linha do tempo do nivel 16 (sync com trava x fila 1 worker x 2 slots)
    tags = [t for t in ("sync_lock", "sync_nolock", "q1_burst", "q2_burst") if data.get(t)]
    if tags:
        fig, axs = plt.subplots(1, len(tags), figsize=(4.2 * len(tags), 4.6), sharey=False)
        axs = np.atleast_1d(axs)
        for ax, t in zip(axs, tags):
            rr = sorted([r for r in data[t]["records"] if r["level"] == 16], key=lambda r: r["t_submit"])
            if not rr:
                continue
            t0 = min(r["t_submit"] for r in rr)
            rr = sorted(rr, key=lambda r: r["t_end"])
            for i, r in enumerate(rr):
                tm = r.get("timings") or {}
                if tm.get("started_at") and tm.get("finished_at"):
                    ax.barh(i, tm["started_at"] - r["t_submit"], left=r["t_submit"] - t0, color="#bbb")
                    ax.barh(i, tm["finished_at"] - tm["started_at"], left=tm["started_at"] - t0, color=COLOR[t])
                else:
                    ax.barh(i, r["t_end"] - r["t_submit"], left=r["t_submit"] - t0,
                            color=COLOR[t] if r.get("ok") else "#000", alpha=0.8)
            ax.set_title(LABEL[t], fontsize=9)
            ax.set_xlabel("tempo desde a rajada (s)")
            ax.set_ylabel("pedido (ordem de término)")
        fig.suptitle("Rajada de 16 clientes: cinza = espera na fila, cor = processamento/conexão presa (preto = erro)",
                     fontsize=10)
        fig.tight_layout()
        fig.savefig(os.path.join(ev_dir, "srv_carga_linha_do_tempo_16.png"), dpi=150)
        plt.close(fig)

    # ---------- grafico 4: memoria de GPU (amostrador nvidia-smi)
    fig, ax = plt.subplots(figsize=(9, 3.8))
    anyp = False
    for t, _, _ in CONFIGS:
        p = os.path.join(res_dir, f"gpu_{t}.csv")
        if not os.path.exists(p):
            continue
        ts, us = [], []
        with open(p) as f:
            for r in csv.DictReader(f):
                try:
                    ts.append(float(r["t"]))
                    us.append(float(r["used_mib"]) / 1024)
                except ValueError:
                    pass
        if ts:
            anyp = True
            ax.plot(np.array(ts) - ts[0], us, color=COLOR[t], label=LABEL[t], lw=1.2)
    if anyp:
        ax.axhline(24, color="k", ls=":", lw=1)
        ax.text(5, 24.3, "teto da frente (24 GB)", fontsize=8)
        ax.set_xlabel("tempo desde o início da rodada (s)")
        ax.set_ylabel("memória de GPU do processo (GB)")
        ax.set_title("Memória de GPU durante o teste de carga (nvidia-smi, por processo)")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(os.path.join(ev_dir, "srv_carga_memoria_gpu.png"), dpi=150)
    plt.close(fig)

    # ---------- cenarios extras: cache, coalescencia, misto (prioridade x FIFO), sonda intensa
    extra = []
    for tag, nome in (("q1_cache", "acerto de cache (mesma imagem+opções)"),
                      ("q1_coalesce", "8 clientes, mesma imagem nova ao mesmo tempo"),
                      ("q1_mixed_prio", "misto 8 clientes, prioridade por preset"),
                      ("q1_mixed_fifo", "misto 8 clientes, FIFO pura"),
                      ("q1_probe", "8 jobs + polling intenso"),
                      ("q1_backpressure", "16 clientes, fila máxima 8 (backpressure)")):
        d = load(res_dir, tag)
        if not d:
            continue
        ok = [r for r in d["records"] if r.get("ok")]
        rej = [r for r in d["records"] if r.get("submit_status") == 429]
        row = dict(cenario=nome, tag=tag, jobs=len(d["records"]), ok=len(ok),
                   lat_p50=round(pct([r["latency_s"] for r in ok], 50), 2),
                   lat_p95=round(pct([r["latency_s"] for r in ok], 95), 2),
                   lat_max=round(max([r["latency_s"] for r in ok]), 2) if ok else "",
                   rejeitados_429=len(rej),
                   resp_429_p50_s=round(pct([r["latency_s"] for r in rej], 50), 2) if rej else "")
        for p in ("rapido", "padrao", "alto"):
            qq = [(r.get("timings") or {}).get("queue_s") for r in ok if r["preset"] == p]
            if qq and "mixed" in tag:
                row[f"fila_{p}_p50"] = round(pct(qq, 50), 1)
                row[f"fila_{p}_max"] = round(max(x for x in qq if x is not None), 1)
        if d["probes"]:
            for r in probe_rows(d, tag):
                row[f"api_{'health' if 'health' in r['rota'] else 'job'}_p95_ms"] = r["p95_ms"]
                row[f"api_{'health' if 'health' in r['rota'] else 'job'}_p99_ms"] = r["p99_ms"]
                row["sonda_req_s"] = r["taxa_req_s"]
        extra.append(row)
    if extra:
        cols = sorted({k for r in extra for k in r}, key=lambda k: (k not in ("cenario", "tag", "jobs", "ok"), k))
        write_table(extra, os.path.join(tab_dir, "carga_cenarios_extras.csv"),
                    os.path.join(tab_dir, "carga_cenarios_extras.md"), cols)

    dm = {t: load(res_dir, t) for t in ("q1_mixed_prio", "q1_mixed_fifo")}
    if all(dm.values()):
        fig, axs = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
        rng = np.random.default_rng(0)
        pres = [p for p in ("rapido", "padrao", "alto")
                if any(r["preset"] == p for t in dm for r in dm[t]["records"])]
        nomes_p = {"rapido": "rápido", "padrao": "padrão", "alto": "alto"}
        for ax, t, nome in zip(axs, dm, ("prioridade por preset (rápido +0 s, padrão +30 s, alto +90 s)",
                                         "FIFO pura (mesmos pedidos, mesma ordem de chegada)")):
            for k, p in enumerate(pres):
                rr = [r for r in dm[t]["records"] if r.get("ok") and r["preset"] == p]
                qq = [x for x in ((r.get("timings") or {}).get("queue_s") for r in rr) if x is not None]
                if qq:
                    ax.boxplot(qq, positions=[k], widths=0.5, showfliers=False)
                    ax.scatter(np.full(len(qq), k) + rng.uniform(-0.12, 0.12, len(qq)), qq, s=16, alpha=0.7)
                    lat = [r["latency_s"] for r in rr]
                    ax.text(k, max(qq) + 6, f"n={len(qq)}\nlatência p50 {np.median(lat):.0f} s", ha="center",
                            fontsize=8)
            ax.set_xticks(range(len(pres)))
            ax.set_xticklabels([nomes_p[p] for p in pres])
            ax.set_ylabel("espera na fila (s)")
            ax.set_ylim(top=165)
            ax.set_title(nome, fontsize=9)
        cont = {p: sum(1 for r in dm["q1_mixed_prio"]["records"] if r["preset"] == p) for p in pres}
        fig.suptitle("Cenário misto (8 clientes x 2 jobs; sorteio semente 7: "
                     + ", ".join(f"{v} {nomes_p[p]}" for p, v in cont.items()) + "): espera na fila por preset",
                     fontsize=10)
        fig.tight_layout()
        fig.savefig(os.path.join(ev_dir, "srv_carga_misto_prioridade.png"), dpi=150)
        plt.close(fig)

    # ---------- backpressure: rajada de 16 com fila maxima 32 (q1_burst L16) x fila maxima 8 (q1_backpressure)
    db = load(res_dir, "q1_backpressure")
    dq16 = load(res_dir, "q1_burst")
    if db and dq16:
        fig, axs = plt.subplots(1, 2, figsize=(11.5, 4.4), sharex=True)
        for ax, (nome, recs) in zip(axs, (("fila máxima 32 (padrão): todos aceitos",
                                           [r for r in dq16["records"] if r["level"] == 16]),
                                          ("fila máxima 8: excedente recusado com 429 + Retry-After",
                                           db["records"]))):
            t0 = min(r["t_submit"] for r in recs)
            recs = sorted(recs, key=lambda r: (r.get("submit_status") != 429, r["t_end"]))
            for i, r in enumerate(recs):
                tm = r.get("timings") or {}
                if r.get("submit_status") == 429:
                    ax.barh(i, max(0.8, r["t_end"] - r["t_submit"]), left=r["t_submit"] - t0, color="#c0392b")
                elif tm.get("started_at") and tm.get("finished_at"):
                    ax.barh(i, tm["started_at"] - r["t_submit"], left=r["t_submit"] - t0, color="#bbb")
                    ax.barh(i, tm["finished_at"] - tm["started_at"], left=tm["started_at"] - t0, color="#2471a3")
            n429 = sum(1 for r in recs if r.get("submit_status") == 429)
            fim = max(r["t_end"] for r in recs) - t0
            ax.set_title(f"{nome}\n{len(recs) - n429} aceitos, {n429} recusados, último termina em {fim:.0f} s",
                         fontsize=9)
            ax.set_xlabel("tempo desde a rajada (s)")
            ax.set_ylabel("pedido")
        fig.suptitle("Backpressure (16 clientes, 1 worker): cinza = fila, azul = GPU, vermelho = 429 imediato",
                     fontsize=10)
        fig.tight_layout()
        fig.savefig(os.path.join(ev_dir, "srv_carga_backpressure.png"), dpi=150)
        plt.close(fig)

    dc, dq = load(res_dir, "q1_cache"), load(res_dir, "q1_burst")
    dco = load(res_dir, "q1_coalesce")
    if dc and dq:
        fig, ax = plt.subplots(figsize=(7.5, 3.8))
        a = [r["latency_s"] for r in dq["records"] if r.get("ok") and r["level"] == 1]
        b = [r["latency_s"] for r in dc["records"] if r.get("ok")]
        vals = [("processado (1 cliente, fila vazia)", a, "#2471a3"), ("acerto de cache", b, "#17a589")]
        if dco:
            vals.append(("coalescido (8 pedidos iguais ao mesmo\ntempo → 1 execução de GPU)",
                         [r["latency_s"] for r in dco["records"] if r.get("ok")],
                         "#8e44ad"))
        for k, (nome, v, c) in enumerate(vals):
            ax.bar(k, np.median(v), color=c, alpha=0.8)
            ax.scatter(np.full(len(v), k), v, color="k", s=10)
            ax.text(k, np.median(v) * 1.15, f"{np.median(v):.2f} s", ha="center", fontsize=9)
        ax.set_yscale("log")
        ax.set_xticks(range(len(vals)))
        ax.set_xticklabels([v[0] for v in vals], fontsize=8)
        ax.set_ylabel("latência ponta a ponta (s, log)")
        ax.set_title("Cache por hash do conteúdo e coalescência de pedidos idênticos")
        fig.tight_layout()
        fig.savefig(os.path.join(ev_dir, "srv_carga_cache.png"), dpi=150)
        plt.close(fig)
    print("ok:", tab_dir, ev_dir)


if __name__ == "__main__":
    main(*sys.argv[1:4])

"""Metricas Prometheus (/metrics).

* HTTP (em memoria, processo da API): contador e histograma de latencia por rota-modelo/metodo/status.
* Fila/jobs/workers (lidos do SQLite a cada coleta, entao refletem tambem o que os workers fizeram):
  tamanho da fila, jobs em execucao, workers/slots vivos, memoria de GPU de cada worker, contadores e
  histogramas persistentes de duracao/espera/latencia por preset.
"""
from __future__ import annotations

import json
import time

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, HistogramMetricFamily

from . import db as D

REGISTRY = CollectorRegistry(auto_describe=True)

HTTP_REQS = Counter("gen3d_http_requests_total", "Requisicoes HTTP", ["method", "route", "status"],
                    registry=REGISTRY)
HTTP_LAT = Histogram("gen3d_http_request_duration_seconds", "Latencia HTTP (s)", ["method", "route"],
                     buckets=(0.002, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 120, 300),
                     registry=REGISTRY)
REJECTED = Counter("gen3d_rejected_total", "Pedidos recusados", ["reason"], registry=REGISTRY)


def _labels(s: str) -> dict:
    out = {}
    for part in s.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
    return out


class DBCollector:
    def __init__(self, dbh: D.ThreadLocalDB, stale_s: float):
        self.dbh, self.stale_s = dbh, stale_s

    def collect(self):
        conn = self.dbh.conn
        qc = D.queue_counts(conn)
        g = GaugeMetricFamily("gen3d_queue_length", "Jobs aguardando na fila (sem contar seguidores identicos)")
        g.add_metric([], qc["queued"])
        yield g
        g = GaugeMetricFamily("gen3d_jobs_running", "Jobs em execucao")
        g.add_metric([], qc["running"])
        yield g
        g = GaugeMetricFamily("gen3d_jobs_coalesced_waiting", "Jobs identicos aguardando o lider")
        g.add_metric([], qc["followers"])
        yield g
        alive = D.alive_workers(conn, self.stale_s)
        g = GaugeMetricFamily("gen3d_workers_alive", "Workers com heartbeat recente")
        g.add_metric([], len(alive))
        yield g
        gs = GaugeMetricFamily("gen3d_worker_slots", "Slots de execucao por worker", labels=["worker", "state"])
        gm = GaugeMetricFamily("gen3d_worker_gpu_memory_gigabytes", "Memoria de GPU do worker (GB)",
                               labels=["worker", "kind"])
        gh = GaugeMetricFamily("gen3d_host_memory_available_gigabytes", "MemAvailable do host visto pelo worker",
                               labels=["worker"])
        gb = GaugeMetricFamily("gen3d_worker_busy_slots", "Slots ocupados", labels=["worker"])
        for w in alive:
            info = json.loads(w.get("info_json") or "{}")
            gs.add_metric([w["id"], w["state"] or "?"], w["slots"] or 0)
            gb.add_metric([w["id"]], w["busy"] or 0)
            for k, v in (info.get("gpu_mem") or {}).items():
                gm.add_metric([w["id"], k.replace("_gb", "")], v)
            if "mem_available_gb" in info:
                gh.add_metric([w["id"]], info["mem_available_gb"])
        yield gs
        yield gb
        yield gm
        yield gh
        rows = conn.execute("SELECT name, labels, value FROM counters").fetchall()
        counters: dict[str, list] = {}
        hists: dict[str, dict] = {}
        ests = GaugeMetricFamily("gen3d_estimated_job_seconds", "Estimativa atual (EMA) da duracao do job",
                                 labels=["preset", "texture"])
        for r in rows:
            name, labels, val = r["name"], r["labels"], r["value"]
            if name == "est_seconds":
                lb = _labels(labels)
                ests.add_metric([lb.get("preset", ""), lb.get("texture", "")], val)
            elif name.endswith("_bucket") or name.endswith("_sum") or name.endswith("_count"):
                base, kind = name.rsplit("_", 1)
                lb = _labels(labels)
                le = lb.pop("le", None)
                key = tuple(sorted(lb.items()))
                h = hists.setdefault(base, {}).setdefault(key, {"buckets": {}, "sum": 0.0, "count": 0.0})
                if kind == "bucket":
                    h["buckets"][le] = val
                elif kind == "sum":
                    h["sum"] = val
                else:
                    h["count"] = val
            else:
                counters.setdefault(name, []).append((_labels(labels), val))
        yield ests
        for name, items in counters.items():
            keys = sorted({k for lb, _ in items for k in lb})
            c = CounterMetricFamily(f"gen3d_{name.removesuffix('_total')}", f"contador persistente {name}",
                                    labels=keys)
            for lb, val in items:
                c.add_metric([lb.get(k, "") for k in keys], val)
            yield c
        for base, series in hists.items():
            keys = sorted({k for key in series for k, _ in key})
            h = HistogramMetricFamily(f"gen3d_{base}", f"histograma persistente {base}", labels=keys)
            for key, d in series.items():
                lb = dict(key)

                def lekey(x):
                    return float("inf") if x == "+Inf" else float(x)
                buckets = sorted(d["buckets"].items(), key=lambda kv: lekey(kv[0]))
                h.add_metric([lb.get(k, "") for k in keys], [(le, v) for le, v in buckets], d["sum"])
            yield h
        g = GaugeMetricFamily("gen3d_scrape_timestamp_seconds", "Momento da coleta")
        g.add_metric([], time.time())
        yield g


def install(dbh: D.ThreadLocalDB, stale_s: float):
    REGISTRY.register(DBCollector(dbh, stale_s))


def render() -> bytes:
    return generate_latest(REGISTRY)

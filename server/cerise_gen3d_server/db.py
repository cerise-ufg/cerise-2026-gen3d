"""Armazenamento persistente dos jobs em SQLite (modo WAL), compartilhado entre a API e os workers.

Por que SQLite (e nao Redis): um unico host (o Spark), poucos jobs por minuto (a GPU processa ~2-3 jobs/min),
necessidade de durabilidade (jobs sobrevivem a restart/queda de energia) e de consultas ricas (posicao na fila,
cache por hash, limpeza por TTL, metricas) sem mais um servico para operar. O SQLite em WAL permite leitores
concorrentes com um escritor, transacoes ACID e `UPDATE ... RETURNING` para o "claim" atomico de jobs por varios
processos. Redis so passaria a valer com varias maquinas de GPU (fila distribuida).
"""
from __future__ import annotations

import heapq
import json
import os
import sqlite3
import threading
import time
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    status        TEXT NOT NULL,              -- queued | running | done | error | cancelled
    preset        TEXT NOT NULL,
    texture       INTEGER NOT NULL DEFAULT 1,
    remove_bg     INTEGER NOT NULL DEFAULT 1,
    options_json  TEXT,
    client        TEXT,                       -- hash do IP/chave (nao guarda IP em claro)
    cache_key     TEXT,
    dedup_of      TEXT,                       -- job "lider" identico em andamento (coalescencia)
    score         REAL NOT NULL,              -- ordem da fila: criado_em + deslocamento do preset
    created_at    REAL NOT NULL,
    started_at    REAL,
    finished_at   REAL,
    updated_at    REAL,
    worker_id     TEXT,
    attempts      INTEGER NOT NULL DEFAULT 0,
    progress      INTEGER NOT NULL DEFAULT 0,
    stage         TEXT,
    error         TEXT,
    job_dir       TEXT,
    input_path    TEXT,
    glb_path      TEXT,
    thumb_path    TEXT,
    stats_json    TEXT,
    cached        INTEGER NOT NULL DEFAULT 0,
    legacy        INTEGER NOT NULL DEFAULT 0,
    image_bytes   INTEGER,
    image_w       INTEGER,
    image_h       INTEGER
);
CREATE INDEX IF NOT EXISTS ix_jobs_queue ON jobs(status, score);
CREATE INDEX IF NOT EXISTS ix_jobs_cache ON jobs(cache_key, status);
CREATE INDEX IF NOT EXISTS ix_jobs_dedup ON jobs(dedup_of);
CREATE INDEX IF NOT EXISTS ix_jobs_created ON jobs(created_at);
CREATE TABLE IF NOT EXISTS workers (
    id          TEXT PRIMARY KEY,
    slots       INTEGER,
    busy        INTEGER,
    presets     TEXT,
    state       TEXT,
    gpu         TEXT,
    model       TEXT,
    started_at  REAL,
    heartbeat   REAL,
    info_json   TEXT
);
CREATE TABLE IF NOT EXISTS counters (
    name    TEXT NOT NULL,
    labels  TEXT NOT NULL DEFAULT '',
    value   REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (name, labels)
);
"""

ACTIVE = ("queued", "running")
FINAL = ("done", "error", "cancelled")

# buckets (s) dos histogramas de duracao/espera exportados no /metrics
DURATION_BUCKETS = (5, 10, 20, 30, 45, 60, 90, 120, 180, 300, 600, 1200)


def connect(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


class ThreadLocalDB:
    """Uma conexao por thread (o pool de threads do FastAPI/uvicorn e as threads dos workers)."""

    def __init__(self, path: str):
        self.path = path
        self._tls = threading.local()
        c = connect(path)
        init_db(c)
        c.close()

    @property
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._tls, "conn", None)
        if c is None:
            c = connect(self.path)
            self._tls.conn = c
        return c


class tx:
    """Transacao IMMEDIATE (trava de escrita desde o inicio: evita corrida entre processos)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self):
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, et, ev, tb):
        self.conn.execute("COMMIT" if et is None else "ROLLBACK")
        return False


def row_to_dict(r: sqlite3.Row | None) -> dict | None:
    return dict(r) if r is not None else None


# ------------------------------------------------------------------------------------------- contadores
def incr(conn, name: str, labels: str = "", value: float = 1.0) -> None:
    conn.execute("INSERT INTO counters(name, labels, value) VALUES(?,?,?) "
                 "ON CONFLICT(name, labels) DO UPDATE SET value = value + excluded.value", (name, labels, value))


def set_counter(conn, name: str, labels: str, value: float) -> None:
    conn.execute("INSERT INTO counters(name, labels, value) VALUES(?,?,?) "
                 "ON CONFLICT(name, labels) DO UPDATE SET value = excluded.value", (name, labels, value))


def get_counter(conn, name: str, labels: str = "", default: float | None = None) -> float | None:
    r = conn.execute("SELECT value FROM counters WHERE name=? AND labels=?", (name, labels)).fetchone()
    return r["value"] if r else default


def observe(conn, name: str, labels: str, value: float, buckets: Iterable[float] = DURATION_BUCKETS) -> None:
    """Histograma cumulativo estilo Prometheus guardado na tabela counters (sobrevive a restart)."""
    sep = "," if labels else ""
    for b in buckets:
        if value <= b:
            incr(conn, name + "_bucket", f"{labels}{sep}le={b}")
    incr(conn, name + "_bucket", f"{labels}{sep}le=+Inf")
    incr(conn, name + "_sum", labels, value)
    incr(conn, name + "_count", labels, 1)


def est_key(preset: str, texture: bool) -> str:
    return f"preset={preset},texture={int(bool(texture))}"


def get_estimate(conn, preset: str, texture: bool, defaults: dict[str, float]) -> float:
    v = get_counter(conn, "est_seconds", est_key(preset, texture))
    if v is not None:
        return float(v)
    base = float(defaults.get(preset, 30.0))
    return base if texture else max(5.0, 0.35 * base)


def update_estimate(conn, preset: str, texture: bool, seconds: float, defaults: dict[str, float],
                    alpha: float = 0.3) -> None:
    old = get_estimate(conn, preset, texture, defaults)
    set_counter(conn, "est_seconds", est_key(preset, texture), (1 - alpha) * old + alpha * seconds)


# ------------------------------------------------------------------------------------------- jobs
def insert_job(conn, job: dict[str, Any]) -> None:
    cols = ",".join(job.keys())
    q = ",".join("?" for _ in job)
    conn.execute(f"INSERT INTO jobs({cols}) VALUES({q})", tuple(job.values()))


def get_job(conn, job_id: str) -> dict | None:
    return row_to_dict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def queue_counts(conn) -> dict[str, int]:
    out = {"queued": 0, "running": 0, "followers": 0}
    for r in conn.execute("SELECT status, dedup_of IS NOT NULL AS f, COUNT(*) n FROM jobs "
                          "WHERE status IN ('queued','running') GROUP BY status, f"):
        if r["status"] == "queued" and r["f"]:
            out["followers"] += r["n"]
        else:
            out[r["status"]] += r["n"]
    return out


def client_active(conn, client: str) -> int:
    r = conn.execute("SELECT COUNT(*) n FROM jobs WHERE client=? AND status IN ('queued','running')",
                     (client,)).fetchone()
    return int(r["n"])


def find_cached(conn, cache_key: str) -> dict | None:
    for r in conn.execute("SELECT * FROM jobs WHERE cache_key=? AND status='done' ORDER BY finished_at DESC "
                          "LIMIT 5", (cache_key,)):
        if r["glb_path"] and os.path.exists(r["glb_path"]):
            return dict(r)
    return None


def find_inflight(conn, cache_key: str) -> dict | None:
    return row_to_dict(conn.execute(
        "SELECT * FROM jobs WHERE cache_key=? AND status IN ('queued','running') AND dedup_of IS NULL "
        "ORDER BY created_at LIMIT 1", (cache_key,)).fetchone())


def claim_job(conn, worker_id: str, presets: list[str]) -> dict | None:
    """Pega atomicamente o proximo job da fila (menor score) que este worker sabe executar."""
    now = time.time()
    marks = ",".join("?" for _ in presets)
    with tx(conn):
        r = conn.execute(
            f"""UPDATE jobs SET status='running', worker_id=?, started_at=?, updated_at=?,
                    attempts=attempts+1, stage='iniciando', progress=1
                WHERE id = (SELECT id FROM jobs WHERE status='queued' AND dedup_of IS NULL
                            AND preset IN ({marks}) ORDER BY score LIMIT 1)
                RETURNING *""", (worker_id, now, now, *presets)).fetchone()
        return row_to_dict(r)


def set_progress(conn, job_id: str, stage: str, progress: int) -> None:
    conn.execute("UPDATE jobs SET stage=?, progress=?, updated_at=? WHERE id=? AND status='running'",
                 (stage, int(progress), time.time(), job_id))


def _link_or_copy(src: str, dst: str) -> None:
    import shutil
    if os.path.exists(dst):
        os.remove(dst)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def attach_result(job_dir: str, glb_src: str, thumb_src: str | None) -> tuple[str, str | None]:
    """Copia (hardlink) o resultado para a pasta de outro job: cada job tem seus arquivos e o TTL apaga
    cada pasta de forma independente."""
    os.makedirs(job_dir, exist_ok=True)
    glb = os.path.join(job_dir, "model.glb")
    _link_or_copy(glb_src, glb)
    thumb = None
    if thumb_src and os.path.exists(thumb_src):
        thumb = os.path.join(job_dir, "thumbnail.png")
        _link_or_copy(thumb_src, thumb)
    return glb, thumb


def finish_job(conn, job: dict, glb_path: str, thumb_path: str | None, stats: dict,
               defaults: dict[str, float]) -> int:
    """Marca o job como concluido, resolve os seguidores identicos e atualiza estimativas/metricas.
    Retorna o numero de seguidores resolvidos."""
    now = time.time()
    run_s = now - (job.get("started_at") or now)
    wait_s = (job.get("started_at") or now) - job["created_at"]
    followers = conn.execute("SELECT * FROM jobs WHERE dedup_of=? AND status='queued'", (job["id"],)).fetchall()
    links = []
    for f in followers:
        links.append((f, *attach_result(f["job_dir"], glb_path, thumb_path)))
    with tx(conn):
        conn.execute("""UPDATE jobs SET status='done', progress=100, stage='concluido', finished_at=?, updated_at=?,
                        glb_path=?, thumb_path=?, stats_json=?, error=NULL WHERE id=?""",
                     (now, now, glb_path, thumb_path, json.dumps(stats), job["id"]))
        for f, glb, thumb in links:
            fstats = dict(stats, deduplicated_from=job["id"])
            conn.execute("""UPDATE jobs SET status='done', progress=100, stage='concluido', started_at=?,
                            finished_at=?, updated_at=?, glb_path=?, thumb_path=?, stats_json=?, cached=1
                            WHERE id=? AND status='queued'""",
                         (job.get("started_at"), now, now, glb, thumb, json.dumps(fstats), f["id"]))
            incr(conn, "jobs_total", f"status=done,preset={f['preset']},origin=coalesced")
            observe(conn, "job_latency_seconds", f"preset={f['preset']}", now - f["created_at"])
        incr(conn, "jobs_total", f"status=done,preset={job['preset']},origin=computed")
        observe(conn, "job_run_seconds", f"preset={job['preset']}", run_s)
        observe(conn, "job_queue_wait_seconds", f"preset={job['preset']}", wait_s)
        observe(conn, "job_latency_seconds", f"preset={job['preset']}", now - job["created_at"])
        update_estimate(conn, job["preset"], bool(job["texture"]), run_s, defaults)
    return len(links)


def fail_job(conn, job: dict, error: str, requeue: bool, max_attempts: int) -> str:
    """Erro no job. Se `requeue` e ainda ha tentativas, volta para a fila (mesmo score: nao perde a vez)."""
    now = time.time()
    with tx(conn):
        cur = conn.execute("SELECT attempts, status FROM jobs WHERE id=?", (job["id"],)).fetchone()
        if cur is None or cur["status"] != "running":
            return cur["status"] if cur else "missing"
        if requeue and cur["attempts"] < max_attempts:
            conn.execute("""UPDATE jobs SET status='queued', worker_id=NULL, started_at=NULL, progress=0,
                            stage='na fila', updated_at=?, error=? WHERE id=?""", (now, error, job["id"]))
            incr(conn, "jobs_requeued_total", f"preset={job['preset']}")
            return "queued"
        conn.execute("""UPDATE jobs SET status='error', stage='erro', error=?, finished_at=?, updated_at=?
                        WHERE id=?""", (error, now, now, job["id"]))
        # seguidores identicos falham junto (mesma entrada + opcoes)
        conn.execute("""UPDATE jobs SET status='error', stage='erro', error=?, finished_at=?, updated_at=?
                        WHERE dedup_of=? AND status='queued'""", (error, now, now, job["id"]))
        incr(conn, "jobs_total", f"status=error,preset={job['preset']},origin=computed")
        return "error"


def cancel_job(conn, job_id: str) -> tuple[str, dict | None]:
    """Cancela um job ainda na fila. Se ele for lider de seguidores identicos, promove o mais antigo."""
    now = time.time()
    with tx(conn):
        j = row_to_dict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
        if j is None:
            return "missing", None
        if j["status"] != "queued":
            return j["status"], j
        conn.execute("UPDATE jobs SET status='cancelled', stage='cancelado', finished_at=?, updated_at=? "
                     "WHERE id=?", (now, now, job_id))
        if j["dedup_of"] is None:
            fs = conn.execute("SELECT id FROM jobs WHERE dedup_of=? AND status='queued' ORDER BY created_at",
                              (job_id,)).fetchall()
            if fs:
                new_leader = fs[0]["id"]
                conn.execute("UPDATE jobs SET dedup_of=NULL, score=? WHERE id=?", (j["score"], new_leader))
                conn.execute("UPDATE jobs SET dedup_of=? WHERE dedup_of=? AND status='queued'",
                             (new_leader, job_id))
        incr(conn, "jobs_total", f"status=cancelled,preset={j['preset']},origin=client")
        return "cancelled", j


def requeue_worker_jobs(conn, worker_id: str, max_attempts: int, reason: str) -> list[tuple[str, str]]:
    """Recuperacao apos restart/queda: jobs 'running' deste worker voltam para a fila (ou viram erro)."""
    out = []
    for r in conn.execute("SELECT * FROM jobs WHERE status='running' AND worker_id=?", (worker_id,)).fetchall():
        st = fail_job(conn, dict(r), reason, requeue=True, max_attempts=max_attempts)
        out.append((r["id"], st))
    return out


def stale_workers(conn, stale_s: float) -> list[str]:
    lim = time.time() - stale_s
    return [r["id"] for r in conn.execute("SELECT id FROM workers WHERE heartbeat < ?", (lim,))]


def alive_workers(conn, stale_s: float) -> list[dict]:
    lim = time.time() - stale_s
    return [dict(r) for r in conn.execute("SELECT * FROM workers WHERE heartbeat >= ? ORDER BY id", (lim,))]


def upsert_worker(conn, w: dict) -> None:
    cols = ",".join(w.keys())
    q = ",".join("?" for _ in w)
    upd = ",".join(f"{k}=excluded.{k}" for k in w if k != "id")
    conn.execute(f"INSERT INTO workers({cols}) VALUES({q}) ON CONFLICT(id) DO UPDATE SET {upd}", tuple(w.values()))


# ------------------------------------------------------------------------------------------- fila / ETA
def queue_plan(conn, defaults: dict[str, float], slots: int) -> dict[str, tuple[int, float]]:
    """Simula o escalonamento (list scheduling) da fila atual nos `slots` livres:
    devolve {job_id: (posicao 1-based, eta_s ate terminar)} para jobs na fila e em execucao."""
    now = time.time()
    slots = max(1, int(slots))
    running = conn.execute("SELECT id, preset, texture, started_at FROM jobs WHERE status='running' "
                           "ORDER BY started_at").fetchall()
    queued = conn.execute("SELECT id, preset, texture FROM jobs WHERE status='queued' AND dedup_of IS NULL "
                          "ORDER BY score").fetchall()
    est_cache: dict[tuple, float] = {}

    def est(p, t):
        k = (p, bool(t))
        if k not in est_cache:
            est_cache[k] = get_estimate(conn, p, bool(t), defaults)
        return est_cache[k]

    plan: dict[str, tuple[int, float]] = {}
    heap: list[float] = []
    for r in running:
        rem = max(1.0, est(r["preset"], r["texture"]) - (now - (r["started_at"] or now)))
        plan[r["id"]] = (0, rem)
        heap.append(rem)
    heap.sort()
    heap = heap[:slots] if len(heap) >= slots else heap + [0.0] * (slots - len(heap))
    heapq.heapify(heap)
    for i, r in enumerate(queued):
        start = heapq.heappop(heap)
        fin = start + est(r["preset"], r["texture"])
        heapq.heappush(heap, fin)
        plan[r["id"]] = (i + 1, fin)
    return plan


def expired_jobs(conn, cutoff: float) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT id, job_dir, status FROM jobs WHERE created_at < ? AND status NOT IN ('queued','running')",
        (cutoff,))]


def delete_job_row(conn, job_id: str) -> None:
    conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))

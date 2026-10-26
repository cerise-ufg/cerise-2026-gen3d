"""Worker de GPU: carrega o modelo uma vez (quente) e consome a fila persistente (SQLite).

* N slots (GEN3D_WORKER_SLOTS) no mesmo processo, com pesos compartilhados (ver engine.py);
* claim atomico do proximo job (menor score = FIFO com prioridade por preset e envelhecimento);
* recuperacao apos restart: jobs que estavam "running" neste worker voltam para a fila (ate MAX_ATTEMPTS);
* heartbeat a cada 5 s (estado, memoria de GPU, memoria disponivel do host) -> /health e /metrics;
* guarda de memoria: so pega job novo se a memoria "available" do host ficar acima da folga exigida no Spark;
* timeout por preset: se um job passar do limite, ele e marcado como erro e o processo sai (o Docker reinicia o
  worker com `restart: unless-stopped`; nao da para interromper com seguranca um kernel CUDA em andamento);
* parada graciosa (SIGTERM): para de pegar jobs e espera os jobs em andamento terminarem.

Uso: python -m cerise_gen3d_server.worker
"""
from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
import traceback

from . import __version__
from . import db as D
from .common import setup_logging
from .config import settings as S

log = logging.getLogger("gen3d.worker")

JOB_PEAK_DELTA_GB = 3.5   # memoria extra de um job alem do modelo carregado (pico 14,5 - 11,4 GB medidos)
MODEL_LOAD_GB = 16.0      # memoria para carregar forma + paint turbo + paint completo


def mem_available_gb() -> float:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 2 ** 20
    except OSError:
        pass
    return float("inf")


class Worker:
    def __init__(self):
        self.db = D.ThreadLocalDB(S.db_path)
        self.stop = threading.Event()
        self.engine = None
        self.state = "starting"
        self.busy: dict[int, dict] = {}       # slot -> job
        self.jobs_done = 0
        self.jobs_failed = 0
        self.started = time.time()
        self.lock = threading.Lock()
        self.mem_paused = False

    # --------------------------------------------------------------------------------------------- heartbeat
    def heartbeat(self):
        info = dict(version=__version__, pid=os.getpid(), jobs_done=self.jobs_done, jobs_failed=self.jobs_failed,
                    mem_available_gb=round(mem_available_gb(), 2), mem_paused=self.mem_paused,
                    running=[dict(slot=k, job=v["id"], preset=v["preset"]) for k, v in list(self.busy.items())])
        gpu = "?"
        if self.engine is not None:
            info.update(gpu_mem=self.engine.gpu_memory(), load_s=round(self.engine.load_s, 1),
                        warmup_s=round(self.engine.warmup_s, 1),
                        mem_after_load_gb=round(self.engine.mem_after_load_gb, 3))
            gpu = self.engine.gpu_name
        D.upsert_worker(self.db.conn, dict(
            id=S.worker_id, slots=S.worker_slots, busy=len(self.busy), presets=",".join(S.worker_presets),
            state=self.state, gpu=gpu, model=S.model_name, started_at=self.started, heartbeat=time.time(),
            info_json=json.dumps(info)))

    def heartbeat_loop(self):
        while not self.stop.is_set():
            try:
                self.heartbeat()
            except Exception:  # noqa: BLE001
                log.exception("falha no heartbeat")
            self.stop.wait(S.heartbeat_s)

    # --------------------------------------------------------------------------------------------- watchdog
    def watchdog_loop(self):
        while not self.stop.is_set():
            now = time.time()
            for slot, job in list(self.busy.items()):
                limit = S.job_timeouts.get(job["preset"], 600.0)
                if now - job["_t0"] > limit:
                    msg = f"tempo limite excedido ({int(limit)} s) no preset {job['preset']}"
                    log.error("timeout do job; reiniciando o worker", extra=dict(job_id=job["id"], slot=slot,
                                                                                 limit_s=limit))
                    try:
                        D.fail_job(self.db.conn, job, msg, requeue=False, max_attempts=S.max_attempts)
                    finally:
                        os._exit(70)  # Docker reinicia o container (restart: unless-stopped)
            self.stop.wait(2.0)

    # --------------------------------------------------------------------------------------------- slots
    def run_job(self, slot: int, job: dict):
        conn = self.db.conn
        out_dir = os.path.join(job["job_dir"], "out")
        last = {"t": 0.0, "p": -1}

        def progress(stage: str, pct: int):
            now = time.time()
            if pct != last["p"] and (now - last["t"] > 0.3 or pct >= 90):
                last.update(t=now, p=pct)
                D.set_progress(conn, job["id"], stage, pct)

        t0 = time.time()
        res = self.engine.generate(job["input_path"], out_dir, job["preset"], texture=bool(job["texture"]),
                                   remove_background=bool(job["remove_bg"]), progress=progress, slot=slot)
        glb = os.path.join(job["job_dir"], "model.glb")
        os.replace(res["glb_path"], glb)
        thumb = None
        if res.get("thumb_path") and os.path.exists(res["thumb_path"]):
            thumb = os.path.join(job["job_dir"], "thumbnail.png")
            os.replace(res["thumb_path"], thumb)
        stats = dict(res["stats"], worker=S.worker_id, queue_wait_s=round(job["started_at"] - job["created_at"], 3))
        n_f = D.finish_job(conn, job, glb, thumb, stats, S.est_seconds)
        if S.delete_input_after and job.get("input_path"):
            try:
                os.remove(job["input_path"])
            except OSError:
                pass
        try:
            os.rmdir(out_dir) if os.path.isdir(out_dir) and not os.listdir(out_dir) else None
        except OSError:
            pass
        log.info("job concluido", extra=dict(job_id=job["id"], slot=slot, preset=job["preset"],
                                             run_s=round(time.time() - t0, 2), followers=n_f,
                                             glb_bytes=stats.get("glb_bytes"), faces=stats.get("faces"),
                                             queue_wait_s=stats["queue_wait_s"]))

    def slot_loop(self, slot: int):
        conn = self.db.conn
        pause_flag = os.path.join(S.data_dir, "PAUSE")
        while not self.stop.is_set():
            if os.path.exists(pause_flag):  # operacao: `touch data/PAUSE` drena a GPU sem derrubar o servico
                if self.state != "paused" and not self.busy:
                    log.info("worker pausado (arquivo PAUSE)")
                    self.state = "paused"
                self.stop.wait(1.0)
                continue
            if self.state == "paused":
                self.state = "ready"
                log.info("worker retomado")
            avail = mem_available_gb()
            if avail < S.min_available_gb + JOB_PEAK_DELTA_GB:
                if not self.mem_paused:
                    log.warning("memoria do host baixa: pausando novos jobs", extra=dict(available_gb=avail))
                self.mem_paused = True
                self.stop.wait(5.0)
                continue
            if self.mem_paused:
                log.info("memoria normalizada: retomando", extra=dict(available_gb=avail))
            self.mem_paused = False
            try:
                job = D.claim_job(conn, S.worker_id, list(self.engine.presets))
            except Exception:  # noqa: BLE001
                log.exception("falha no claim")
                self.stop.wait(1.0)
                continue
            if job is None:
                self.stop.wait(S.poll_interval_s)
                continue
            job["_t0"] = time.time()
            with self.lock:
                self.busy[slot] = job
                self.state = "busy"
            log.info("job iniciado", extra=dict(job_id=job["id"], slot=slot, preset=job["preset"],
                                                attempt=job["attempts"],
                                                queue_wait_s=round(job["started_at"] - job["created_at"], 3)))
            try:
                self.run_job(slot, job)
                self.jobs_done += 1
            except Exception as e:  # noqa: BLE001
                self.jobs_failed += 1
                tb = traceback.format_exc()
                oom = "out of memory" in str(e).lower()
                msg = ("memória de GPU insuficiente no momento; tente novamente" if oom
                       else f"falha na geração: {type(e).__name__}: {str(e)[:300]}")
                st = D.fail_job(conn, job, msg, requeue=oom, max_attempts=S.max_attempts)
                log.error("job falhou", extra=dict(job_id=job["id"], slot=slot, new_status=st, error=msg,
                                                   trace=tb[-2000:]))
                if oom:
                    try:
                        self.engine.torch.cuda.empty_cache()
                    except Exception:  # noqa: BLE001
                        pass
            finally:
                with self.lock:
                    self.busy.pop(slot, None)
                    self.state = "busy" if self.busy else "ready"
                    idle = not self.busy
                if idle and D.queue_counts(conn)["queued"] == 0:
                    try:  # ocioso: devolve o cache do alocador (memoria unificada compartilhada com a producao)
                        self.engine.release_cache()
                    except Exception:  # noqa: BLE001
                        pass

    # --------------------------------------------------------------------------------------------- main
    def run(self):
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, lambda *_: self._sigterm())
            signal.signal(signal.SIGINT, lambda *_: self._sigterm())
        conn = self.db.conn
        rec = D.requeue_worker_jobs(conn, S.worker_id, S.max_attempts,
                                    "worker reiniciado durante o processamento; job reenfileirado")
        if rec:
            log.warning("jobs recuperados apos restart", extra=dict(jobs=rec))
        self.state = "loading"
        hb = threading.Thread(target=self.heartbeat_loop, daemon=True, name="heartbeat")
        hb.start()
        # guarda de memoria antes de carregar o modelo (regra do Spark: folga >= 10 GB alem do que vamos usar)
        need = S.min_available_gb + (0 if S.fake_engine else MODEL_LOAD_GB)
        while mem_available_gb() < need and not self.stop.is_set():
            log.warning("aguardando memoria para carregar o modelo",
                        extra=dict(available_gb=round(mem_available_gb(), 1), need_gb=need))
            self.stop.wait(15)
        t0 = time.time()
        if S.fake_engine:
            from .engine import FakeEngine
            self.engine = FakeEngine(S.worker_presets, slots=S.worker_slots, seconds=S.fake_seconds)
        else:
            from .engine import Engine
            self.engine = Engine(S.worker_presets, slots=S.worker_slots, gpu_cap_gb=S.gpu_cap_gb,
                                 warmup_presets=S.warmup_presets)
        log.info("modelo carregado", extra=dict(worker=S.worker_id, slots=S.worker_slots,
                                                presets=list(self.engine.presets), init_s=round(time.time() - t0, 1),
                                                load_s=round(self.engine.load_s, 1),
                                                warmup_s=round(self.engine.warmup_s, 1),
                                                gpu=self.engine.gpu_name, gpu_mem=self.engine.gpu_memory()))
        # jobs que ficaram "running" de novo enquanto carregava (ex.: outro restart) tambem voltam
        D.requeue_worker_jobs(conn, S.worker_id, S.max_attempts, "worker reiniciado; job reenfileirado")
        self.state = "ready"
        self.heartbeat()
        threading.Thread(target=self.watchdog_loop, daemon=True, name="watchdog").start()
        slots = [threading.Thread(target=self.slot_loop, args=(i,), name=f"slot{i}") for i in range(S.worker_slots)]
        for t in slots:
            t.start()
        for t in slots:
            while t.is_alive():
                t.join(1.0)
        self.state = "stopped"
        try:
            self.heartbeat()
        except Exception:  # noqa: BLE001
            pass
        log.info("worker encerrado", extra=dict(jobs_done=self.jobs_done, jobs_failed=self.jobs_failed))

    def _sigterm(self):
        log.info("SIGTERM: parando de pegar jobs; aguardando os jobs em andamento",
                 extra=dict(running=[j["id"] for j in self.busy.values()]))
        self.state = "stopping"
        self.stop.set()


def main():
    setup_logging("gen3d.worker")
    Worker().run()


if __name__ == "__main__":
    main()

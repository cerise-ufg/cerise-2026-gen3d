"""Teste de carga do servidor de geracao 3D (asyncio + httpx).

Cenarios:
  burst   niveis de N clientes simultaneos (ex.: 1,2,4,8,16), cada um envia 1 job (no nivel 1, `--seq1` jobs em
          sequencia). Mede latencia ponta a ponta (envio -> GLB baixado), espera na fila, vazao, erros.
  mixed   N clientes, cada um envia `--jobs-per-client` jobs em sequencia com presets sorteados (`--mix`).
  cache   reenvia imagens ja processadas (acertos de cache) e mede a latencia.
  coalesce N clientes enviam AO MESMO TEMPO a mesma imagem nova (coalescencia de pedidos identicos).
Em todos, uma tarefa "sonda" mede a responsividade da API em paralelo (GET /api/v1/health e
GET /api/v1/jobs/{id} na fila nova; GET / no servidor sincrono de 2025) a uma taxa fixa.

Modo `--mode queue` (API nova, assincrona) ou `--mode sync` (servidor estilo 2025: POST / segura a conexao).
Cada cliente simulado usa um X-Forwarded-For proprio (a API do teste roda com GEN3D_TRUST_PROXY=1), entao os
limites por cliente continuam ativos durante o teste.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import statistics
import time

import httpx


def now():
    return time.time()


class Pool:
    def __init__(self, folder: str, start: int = 0):
        exts = (".png", ".jpg", ".jpeg")
        self.files = sorted(os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(exts))
        self.i = start

    def next(self) -> str:
        if self.i >= len(self.files):
            raise RuntimeError("pool de imagens esgotado (aumente o pool ou use --pool-start)")
        f = self.files[self.i]
        self.i += 1
        return f


def mime(path: str) -> str:
    return "image/png" if path.lower().endswith(".png") else "image/jpeg"


class Runner:
    def __init__(self, a):
        self.a = a
        self.base = a.base.rstrip("/")
        self.records: list[dict] = []
        self.probes: list[dict] = []
        self.active_ids: list[str] = []
        self.events: list[dict] = []
        lim = httpx.Limits(max_connections=400, max_keepalive_connections=100)
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(a.client_timeout, connect=30), limits=lim)

    def save(self, rec: dict, content: bytes):
        if self.a.save_dir:
            os.makedirs(self.a.save_dir, exist_ok=True)
            p = os.path.join(self.a.save_dir, f"{rec['tag']}_L{rec['level']}_{rec['image']}_{hashlib.sha256(content).hexdigest()[:8]}_{random.randint(0, 9999):04d}.glb")
            with open(p, "wb") as f:
                f.write(content)
            rec["saved"] = os.path.basename(p)

    # ------------------------------------------------------------------------------------------- jobs
    async def job_queue(self, img: str, preset: str, client_ip: str, level: int, tag: str) -> dict:
        rec = dict(mode="queue", image=os.path.basename(img), preset=preset, client=client_ip, level=level,
                   tag=tag, t_submit=now())
        h = {"X-Forwarded-For": client_ip}
        try:
            with open(img, "rb") as f:
                data = f.read()
            opts = {"preset": preset, "texture": True, "remove_background": True}
            r = await self.http.post(self.base + "/api/v1/jobs", headers=h,
                                     files={"image": (os.path.basename(img), data, mime(img))},
                                     data={"options": json.dumps(opts)})
            rec["t_accepted"] = now()
            rec["submit_status"] = r.status_code
            if r.status_code != 202:
                rec.update(ok=False, error=f"HTTP {r.status_code}: {r.text[:200]}", t_end=now())
                return rec
            b = r.json()
            rec.update(job_id=b["job_id"], pos0=b.get("position"), eta0=b.get("eta_seconds"),
                       cached=b.get("cached", False), dedup=b.get("deduplicated", False))
            self.active_ids.append(b["job_id"])
            last = None
            while True:
                if now() - rec["t_submit"] > self.a.client_timeout:
                    rec.update(ok=False, error="timeout do cliente", t_end=now())
                    return rec
                try:
                    g = await self.http.get(f"{self.base}/api/v1/jobs/{b['job_id']}", headers=h)
                except httpx.HTTPError as e:
                    rec.setdefault("poll_errors", 0)
                    rec["poll_errors"] += 1
                    await asyncio.sleep(self.a.poll)
                    continue
                if g.status_code != 200:
                    rec.setdefault("poll_errors", 0)
                    rec["poll_errors"] += 1
                    await asyncio.sleep(self.a.poll)
                    continue
                last = g.json()
                if last["status"] == "running" and "t_running_seen" not in rec:
                    rec["t_running_seen"] = now()
                if last["status"] in ("done", "error", "cancelled"):
                    break
                await asyncio.sleep(self.a.poll)
            rec["final_status"] = last["status"]
            rec["timings"] = last.get("timings")
            if last["status"] != "done":
                rec.update(ok=False, error=last.get("error"), t_end=now())
                return rec
            st = last["result"]["stats"]
            rec["stats"] = {k: st.get(k) for k in ("seconds", "total_s", "faces", "glb_bytes", "dims_m",
                                                   "peak_gpu_gb", "slot", "worker", "lock_waits", "times",
                                                   "cached", "queue_wait_s", "deduplicated_from", "cached_from")}
            t_dl = now()
            gl = await self.http.get(self.base + last["result"]["glb_url"], headers=h)
            rec["download_s"] = now() - t_dl
            rec["glb_bytes"] = len(gl.content)
            rec["glb_sha"] = hashlib.sha256(gl.content).hexdigest()
            rec["ok"] = gl.status_code == 200 and gl.content[:4] == b"glTF"
            self.save(rec, gl.content)
            rec["t_end"] = now()
        except Exception as e:  # noqa: BLE001
            rec.update(ok=False, error=f"{type(e).__name__}: {e}", t_end=now())
        finally:
            if rec.get("job_id") in self.active_ids:
                self.active_ids.remove(rec["job_id"])
        return rec

    async def job_sync(self, img: str, preset: str, client_ip: str, level: int, tag: str) -> dict:
        rec = dict(mode="sync", image=os.path.basename(img), preset=preset, client=client_ip, level=level, tag=tag,
                   t_submit=now())
        try:
            with open(img, "rb") as f:
                data = f.read()
            name = f"front_{int(rec['t_submit'] * 1000)}_{random.randint(0, 1 << 30)}{os.path.splitext(img)[1]}"
            meta = json.dumps({"front": name, "view_type": "single_view"})
            r = await self.http.post(self.base + "/", files={"front": (name, data, mime(img))},
                                     data={"metadata": meta, "view_type": "single_view"},
                                     headers={"X-Forwarded-For": client_ip})
            rec["submit_status"] = r.status_code
            rec["t_end"] = now()
            if r.status_code == 200 and r.content[:4] == b"glTF":
                rec["ok"] = True
                rec["glb_bytes"] = len(r.content)
                rec["glb_sha"] = hashlib.sha256(r.content).hexdigest()
                self.save(rec, r.content)
                rec["server_seconds"] = float(r.headers.get("x-server-seconds", "nan"))
                rec["sha_gerado"] = r.headers.get("x-glb-sha-gerado")
                rec["max_concorrencia"] = r.headers.get("x-max-concorrencia")
                rec["arquivo_trocado"] = bool(rec["sha_gerado"]) and rec["sha_gerado"] != rec["glb_sha"]
                rec["job_id"] = r.headers.get("x-job-id")
            else:
                rec["ok"] = False
                rec["error"] = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:  # noqa: BLE001
            rec.update(ok=False, error=f"{type(e).__name__}: {e}", t_end=now())
        return rec

    async def job(self, *args):
        fn = self.job_queue if self.a.mode == "queue" else self.job_sync
        rec = await fn(*args)
        rec["latency_s"] = rec["t_end"] - rec["t_submit"]
        self.records.append(rec)
        print(f"  [{rec['tag']} L{rec['level']}] {rec['image'][:28]:28s} {rec['preset']:6s} "
              f"ok={rec.get('ok')} lat={rec['latency_s']:.1f}s {rec.get('error') or ''}"[:160], flush=True)
        return rec

    # ------------------------------------------------------------------------------------------- sonda
    async def prober(self, stop: asyncio.Event):
        if self.a.probe_rate <= 0:
            return
        period = 1.0 / self.a.probe_rate
        k = 0
        tasks = set()

        async def one(kind, url):
            t0 = now()
            try:
                r = await self.http.get(url, timeout=30)
                st = r.status_code
            except Exception as e:  # noqa: BLE001
                st = f"exc:{type(e).__name__}"
            self.probes.append(dict(kind=kind, t=t0, latency_s=now() - t0, status=st))

        nxt = now()
        while not stop.is_set():
            if self.a.mode == "queue":
                if k % 2 == 0 or not self.active_ids:
                    kind, url = "health", self.base + "/api/v1/health"
                else:
                    kind, url = "job", f"{self.base}/api/v1/jobs/{random.choice(self.active_ids)}"
            else:
                kind, url = "index", self.base + "/"
            k += 1
            t = asyncio.create_task(one(kind, url))  # laco aberto: nao espera a resposta para a proxima
            tasks.add(t)
            t.add_done_callback(tasks.discard)
            nxt += period
            await asyncio.sleep(max(0.0, nxt - now()))
        if tasks:
            await asyncio.wait(tasks, timeout=35)

    # ------------------------------------------------------------------------------------------- cenarios
    async def run(self):
        a = self.a
        stop = asyncio.Event()
        probe = asyncio.create_task(self.prober(stop))
        pool = Pool(a.images, a.pool_start)
        t_start = now()
        rnd = random.Random(a.seed)
        try:
            if a.scenario == "burst":
                for lvl in [int(x) for x in a.levels.split(",")]:
                    self.events.append(dict(event="level_start", level=lvl, t=now()))
                    print(f"== nivel {lvl} clientes", flush=True)
                    if lvl == 1 and a.seq1 > 1:
                        for k in range(a.seq1):
                            await self.job(pool.next(), a.preset, "10.77.1.1", 1, a.tag)
                    else:
                        imgs = [pool.next() for _ in range(lvl)]
                        await asyncio.gather(*[self.job(imgs[i], a.preset, f"10.77.{lvl}.{i + 1}", lvl, a.tag)
                                               for i in range(lvl)])
                    self.events.append(dict(event="level_end", level=lvl, t=now()))
                    if a.pause_between > 0:
                        await asyncio.sleep(a.pause_between)
            elif a.scenario == "mixed":
                mix = [(p, float(w)) for p, w in (x.split(":") for x in a.mix.split(","))]
                plan = [[rnd.choices([p for p, _ in mix], [w for _, w in mix])[0] for _ in range(a.jobs_per_client)]
                        for _ in range(a.clients)]
                imgs = [[pool.next() for _ in range(a.jobs_per_client)] for _ in range(a.clients)]

                async def client(i):
                    for k in range(a.jobs_per_client):
                        await self.job(imgs[i][k], plan[i][k], f"10.78.0.{i + 1}", a.clients, a.tag)
                self.events.append(dict(event="level_start", level=a.clients, t=now(), plan=plan))
                await asyncio.gather(*[client(i) for i in range(a.clients)])
                self.events.append(dict(event="level_end", level=a.clients, t=now()))
            elif a.scenario == "cache":
                files = sorted(os.listdir(a.images))[a.pool_start:a.pool_start + a.clients]
                for k, f in enumerate(files):
                    await self.job(os.path.join(a.images, f), a.preset, f"10.79.0.{k + 1}", 1, a.tag)
            elif a.scenario == "coalesce":
                img = pool.next()
                self.events.append(dict(event="level_start", level=a.clients, t=now()))
                await asyncio.gather(*[self.job(img, a.preset, f"10.80.0.{i + 1}", a.clients, a.tag)
                                       for i in range(a.clients)])
                self.events.append(dict(event="level_end", level=a.clients, t=now()))
            elif a.scenario == "probe":
                await asyncio.sleep(a.duration)
        finally:
            stop.set()
            await probe
            await self.http.aclose()
        out = dict(args=vars(a), t_start=t_start, t_end=now(), records=self.records, probes=self.probes,
                   events=self.events)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w") as f:
            json.dump(out, f, indent=1)
        ok = [r for r in self.records if r.get("ok")]
        lat = sorted(r["latency_s"] for r in ok)
        print(f"== {a.tag}: {len(ok)}/{len(self.records)} ok; latencia mediana "
              f"{statistics.median(lat) if lat else float('nan'):.1f} s; sondas {len(self.probes)} -> {a.out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=["burst", "mixed", "cache", "coalesce", "probe"])
    ap.add_argument("--base", default="http://127.0.0.1:8095")
    ap.add_argument("--mode", choices=["queue", "sync"], default="queue")
    ap.add_argument("--images", required=True)
    ap.add_argument("--pool-start", type=int, default=0)
    ap.add_argument("--levels", default="1,2,4,8,16")
    ap.add_argument("--seq1", type=int, default=3)
    ap.add_argument("--preset", default="rapido")
    ap.add_argument("--clients", type=int, default=8)
    ap.add_argument("--jobs-per-client", type=int, default=2)
    ap.add_argument("--mix", default="rapido:0.5,padrao:0.35,alto:0.15")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--poll", type=float, default=1.0)
    ap.add_argument("--probe-rate", type=float, default=10.0)
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--client-timeout", type=float, default=900.0)
    ap.add_argument("--pause-between", type=float, default=0.0)
    ap.add_argument("--tag", default="run")
    ap.add_argument("--save-dir", default="")
    ap.add_argument("--out", required=True)
    asyncio.run(Runner(ap.parse_args()).run())


if __name__ == "__main__":
    main()

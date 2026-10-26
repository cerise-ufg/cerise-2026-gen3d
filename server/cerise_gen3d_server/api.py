"""API HTTP do servidor de geracao 3D do CERISE (FastAPI + uvicorn).

Contrato /api/v1 (fixo, compartilhado com o app React Native/Expo) + endpoint legado do app Android de 2025.
A API nao toca na GPU: valida, normaliza e enfileira a foto no SQLite; os workers de GPU consomem a fila.

Executar: uvicorn cerise_gen3d_server.api:app --host 0.0.0.0 --port 8095
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import threading
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile as StarletteUploadFile

from . import __version__
from . import db as D
from . import metrics as M
from .common import ImageError, TokenBucket, client_hash, normalize_image, setup_logging
from .config import settings as S

log = logging.getLogger("gen3d.api")

dbh: D.ThreadLocalDB | None = None
rl_jobs = TokenBucket(S.rate_jobs_per_min, S.rate_jobs_burst)
rl_reads = TokenBucket(S.rate_reads_per_min, S.rate_reads_burst)
_plan_cache: dict = {"t": 0.0, "plan": {}, "slots": 1}
_enqueue_lock = threading.Lock()


def conn():
    return dbh.conn  # type: ignore[union-attr]


# --------------------------------------------------------------------------------------------- janitor
def janitor_once() -> dict:
    """Limpeza periodica: TTL de 7 dias (fotos e modelos), jobs esquecidos na fila, workers mortos."""
    c = conn()
    now = time.time()
    out = {"expired": 0, "queue_timeout": 0, "requeued": 0, "orphans": 0}
    cutoff = now - S.retention_days * 86400
    for j in D.expired_jobs(c, cutoff):
        if j["job_dir"] and os.path.isdir(j["job_dir"]):
            shutil.rmtree(j["job_dir"], ignore_errors=True)
        D.delete_job_row(c, j["id"])
        out["expired"] += 1
    if out["expired"]:
        D.incr(c, "retention_deleted_total", "", out["expired"])
    # jobs na fila ha tempo demais (ninguem processou: worker parado/sem memoria) -> erro explicito
    for r in c.execute("SELECT * FROM jobs WHERE status='queued' AND created_at < ?",
                       (now - S.queue_timeout_s,)).fetchall():
        c.execute("UPDATE jobs SET status='error', stage='erro', error=?, finished_at=?, updated_at=? "
                  "WHERE id=? AND status='queued'",
                  (f"expirou na fila após {int(S.queue_timeout_s)} s sem worker disponível", now, now, r["id"]))
        D.incr(c, "jobs_total", f"status=error,preset={r['preset']},origin=queue_timeout")
        out["queue_timeout"] += 1
    # workers sem heartbeat: jobs "running" deles voltam para a fila
    for wid in D.stale_workers(c, S.worker_stale_s):
        res = D.requeue_worker_jobs(c, wid, S.max_attempts, "worker parou de responder; job reenfileirado")
        out["requeued"] += len(res)
    # pastas orfas (sem linha no banco) com mais de 1 dia
    if os.path.isdir(S.jobs_dir):
        known = {r["id"] for r in c.execute("SELECT id FROM jobs")}
        for name in os.listdir(S.jobs_dir):
            p = os.path.join(S.jobs_dir, name)
            if name not in known and os.path.isdir(p) and now - os.path.getmtime(p) > 86400:
                shutil.rmtree(p, ignore_errors=True)
                out["orphans"] += 1
    if any(out.values()):
        log.info("limpeza", extra=out)
    return out


async def janitor_loop():
    while True:
        try:
            await run_in_threadpool(janitor_once)
        except Exception:  # noqa: BLE001
            log.exception("falha na limpeza")
        await asyncio.sleep(S.janitor_interval_s)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global dbh
    setup_logging("gen3d.api")
    os.makedirs(S.jobs_dir, exist_ok=True)
    dbh = D.ThreadLocalDB(S.db_path)
    try:
        M.install(dbh, S.worker_stale_s)
    except ValueError:
        pass  # ja registrado (testes recriam o app)
    task = asyncio.create_task(janitor_loop())
    log.info("api iniciada", extra=dict(version=__version__, db=S.db_path, max_queue=S.max_queue,
                                        retention_days=S.retention_days, cache=S.cache_enabled,
                                        api_keys=len(S.api_keys)))
    yield
    task.cancel()


DESCRIPTION = """
Servidor de **geração 3D** do CERISE (EMC/UFG): recebe a foto de um objeto e devolve um modelo **GLB texturizado**
(Hunyuan3D-2 Turbo + pós-processamento para celular: Y para cima, apoiado em y=0, maior dimensão 0,30 m, textura JPEG,
sem Draco/meshopt/KTX2).

Fluxo assíncrono: `POST /api/v1/jobs` -> `202 {job_id}` -> *polling* em `GET /api/v1/jobs/{id}` -> download do
`model.glb` e da `thumbnail.png`. A fila é persistente (SQLite) e processada por worker(s) de GPU com o modelo quente.

Limites: imagem JPEG/PNG até 15 MB; fila máxima (429 quando cheia); rate limit por cliente (429 + `Retry-After`).
Privacidade: a foto é apagada após o processamento e os modelos são apagados em até 7 dias.
"""

app = FastAPI(title="CERISE - Servidor de Geração 3D", version=__version__, description=DESCRIPTION,
              lifespan=lifespan, docs_url="/docs", redoc_url=None, openapi_url="/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=S.cors_origins, allow_methods=["GET", "POST", "DELETE"],
                   allow_headers=["*"], expose_headers=["Retry-After", "X-Job-Id"])


def client_ip(request: Request) -> str:
    if S.trust_proxy:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "?"


def client_key(request: Request) -> str:
    k = request.headers.get("x-api-key")
    if k and k in S.api_keys:
        return client_hash("key:" + k)
    return client_hash("ip:" + client_ip(request))


def route_template(request: Request) -> str:
    """Rota-modelo (ex.: /api/v1/jobs/{job_id}) para rotular metricas sem explodir a cardinalidade."""
    from starlette.routing import Match
    r = request.scope.get("route")
    if r is not None and getattr(r, "path", None):
        return r.path
    for route in app.router.routes:
        try:
            m, _ = route.matches(request.scope)
        except Exception:  # noqa: BLE001
            continue
        if m == Match.FULL:
            return getattr(route, "path", "outro")
    return "outro"


@app.middleware("http")
async def mw(request: Request, call_next):
    t0 = time.perf_counter()
    path = request.url.path
    # limite de corpo pelo Content-Length (antes de o multipart ser lido)
    if request.method == "POST":
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > S.max_upload_bytes + 256 * 1024:
            M.REJECTED.labels("too_large").inc()
            return JSONResponse({"detail": f"A imagem é grande demais (max. {S.max_upload_bytes // 2**20} MB)."},
                                status_code=413)
    # autenticacao opcional por chave (so quando GEN3D_API_KEYS estiver definido)
    if S.api_keys and (path.startswith("/api/") or (path == "/" and request.method == "POST")) \
            and path != "/api/v1/health":
        if request.headers.get("x-api-key") not in S.api_keys:
            M.REJECTED.labels("auth").inc()
            return JSONResponse({"detail": "Chave de API ausente ou inválida (cabeçalho X-API-Key)."},
                                status_code=401)
    # rate limit de leituras (polling) por cliente
    if request.method == "GET" and path.startswith("/api/"):
        ok, retry = rl_reads.allow(client_key(request))
        if not ok:
            M.REJECTED.labels("rate_limit_reads").inc()
            return JSONResponse({"detail": "Muitas requisições. Aguarde alguns segundos."}, status_code=429,
                                headers={"Retry-After": str(max(1, int(retry + 0.999)))})
    status = 500
    try:
        resp = await call_next(request)
        status = resp.status_code
        return resp
    finally:
        dt = time.perf_counter() - t0
        rpath = route_template(request)
        M.HTTP_REQS.labels(request.method, rpath, str(status)).inc()
        M.HTTP_LAT.labels(request.method, rpath).observe(dt)
        if not (rpath in ("/api/v1/jobs/{job_id}", "/api/v1/health", "/metrics") and status < 400):
            log.info("http", extra=dict(method=request.method, route=rpath, status=status,
                                        ms=round(dt * 1000, 2), client=client_key(request)[:10]))


# --------------------------------------------------------------------------------------------- helpers
def total_slots(c) -> int:
    return sum(int(w["slots"] or 0) for w in D.alive_workers(c, S.worker_stale_s)
               if w["state"] in ("ready", "busy", "loading", "starting", "paused")) or 1


def get_plan(c, max_age: float = 0.5) -> dict:
    """Plano da fila (posicao/ETA) com cache curto: o polling intenso nao recalcula a cada requisicao."""
    now = time.monotonic()
    if now - _plan_cache["t"] > max_age:
        slots = total_slots(c)
        _plan_cache.update(t=now, plan=D.queue_plan(c, S.est_seconds, slots), slots=slots)
    return _plan_cache["plan"]


def invalidate_plan():
    _plan_cache["t"] = 0.0


def public_job(c, j: dict) -> dict:
    plan = get_plan(c)
    lead = j["dedup_of"] or j["id"]
    pos, eta = plan.get(lead, (0, 0.0))
    st = j["status"]
    result = None
    if st == "done":
        stats = json.loads(j["stats_json"] or "{}")
        stats["cached"] = bool(j["cached"])
        result = {"glb_url": f"/api/v1/jobs/{j['id']}/model.glb",
                  "thumbnail_url": f"/api/v1/jobs/{j['id']}/thumbnail.png", "stats": stats}
    stage = j["stage"] or {"queued": "na fila", "done": "concluido", "error": "erro",
                           "cancelled": "cancelado"}.get(st, st)
    if st == "queued":
        stage = "na fila" if not j["dedup_of"] else "aguardando pedido idêntico"
    return {
        "job_id": j["id"], "status": st,
        "progress": 100 if st == "done" else int(j["progress"] or 0),
        "stage": stage,
        "position": int(pos) if st == "queued" else 0,
        "eta_seconds": round(float(eta), 1) if st in ("queued", "running") else 0.0,
        "error": j["error"] if st == "error" else None,
        "result": result,
        "preset": j["preset"],
        "options": json.loads(j["options_json"] or "{}"),
        "cached": bool(j["cached"]),
        "timings": {"created_at": j["created_at"], "started_at": j["started_at"], "finished_at": j["finished_at"],
                    "queue_s": round(j["started_at"] - j["created_at"], 3) if j["started_at"] else None,
                    "run_s": round(j["finished_at"] - j["started_at"], 3)
                    if j["finished_at"] and j["started_at"] else None},
    }


def parse_options(raw: str | None) -> dict:
    opts = {"preset": "padrao", "texture": True, "remove_background": True}
    if raw:
        try:
            o = json.loads(raw)
        except json.JSONDecodeError as e:
            raise HTTPException(400, f"Campo 'options' não é um JSON válido: {e.msg}") from e
        if not isinstance(o, dict):
            raise HTTPException(400, "Campo 'options' deve ser um objeto JSON.")
        if "preset" in o:
            opts["preset"] = str(o["preset"])
        for k in ("texture", "remove_background"):
            if k in o:
                if not isinstance(o[k], bool):
                    raise HTTPException(400, f"Opcao '{k}' deve ser true/false.")
                opts[k] = o[k]
    if opts["preset"] not in S.presets:
        raise HTTPException(400, f"Preset inválido: '{opts['preset']}'. Use: {', '.join(S.presets)}.")
    return opts


def _enqueue_sync(data: bytes, opts: dict, client: str, legacy: bool) -> tuple[int, dict]:
    """Valida/normaliza e cria o job (roda no pool de threads). Retorna (status_http, corpo)."""
    c = conn()
    now = time.time()
    cache_key = hashlib.sha256(data + b"|" + json.dumps(opts, sort_keys=True).encode() + b"|" +
                               S.pipeline_version.encode()).hexdigest()
    job_id = uuid.uuid4().hex
    job_dir = os.path.join(S.jobs_dir, job_id)
    base = dict(id=job_id, preset=opts["preset"], texture=int(opts["texture"]),
                remove_bg=int(opts["remove_background"]), options_json=json.dumps(opts), client=client,
                cache_key=cache_key, score=now + S.priority_offsets.get(opts["preset"], 0.0), created_at=now,
                updated_at=now, job_dir=job_dir, legacy=int(legacy), image_bytes=len(data))
    def cache_hit_response() -> tuple[int, dict] | None:
        hit = D.find_cached(c, cache_key)
        if not hit:
            return None
        glb, thumb = D.attach_result(job_dir, hit["glb_path"], hit["thumb_path"])
        stats = dict(json.loads(hit["stats_json"] or "{}"), cached_from=hit["id"])
        D.insert_job(c, dict(base, status="done", progress=100, stage="concluido", started_at=now,
                             finished_at=now, glb_path=glb, thumb_path=thumb, stats_json=json.dumps(stats),
                             cached=1))
        D.incr(c, "jobs_total", f"status=done,preset={opts['preset']},origin=cache")
        D.incr(c, "cache_hits_total", f"preset={opts['preset']}")
        invalidate_plan()
        return 202, {"job_id": job_id, "status": "done", "position": 0, "eta_seconds": 0.0, "cached": True}

    # 1) cache: mesma imagem + opcoes ja processada -> resposta imediata (sem GPU, sem ocupar a fila)
    if S.cache_enabled:
        r = cache_hit_response()
        if r:
            return r
    # 2) normaliza a imagem (EXIF, sem metadados, <= 2048 px) fora da secao critica
    try:
        png, info = normalize_image(data, S.max_pixels, S.min_side, S.norm_max_side)
    except ImageError as e:
        M.REJECTED.labels("invalid_image").inc()
        return 400, {"detail": f"Imagem inválida: {e}"}
    with _enqueue_lock:  # decisao cache/coalescencia/backpressure + insercao sem corrida entre requisicoes
        if S.cache_enabled:
            r = cache_hit_response()
            if r:
                return r
        # 3) mesmo pedido ja em andamento: o mesmo cliente recebe o mesmo job (reenvio idempotente);
        #    outro cliente vira "seguidor" e recebe o resultado quando o lider terminar (sem GPU extra)
        leader = D.find_inflight(c, cache_key) if S.cache_enabled else None
        if leader and leader["client"] == client:
            pj = public_job(c, leader)
            return 202, {"job_id": leader["id"], "status": pj["status"], "position": pj["position"],
                         "eta_seconds": pj["eta_seconds"], "deduplicated": True}
        # 4) backpressure: fila cheia ou cliente com pedidos demais em andamento -> 429
        if not leader:
            qc = D.queue_counts(c)
            if qc["queued"] >= S.max_queue:
                M.REJECTED.labels("queue_full").inc()
                return 429, {"detail": "Fila do servidor cheia. Tente novamente em instantes.",
                             "_retry": 30, "queue_length": qc["queued"]}
        if D.client_active(c, client) >= S.max_queued_per_client:
            M.REJECTED.labels("client_cap").inc()
            return 429, {"detail": f"Você já tem {S.max_queued_per_client} pedidos em andamento. "
                                   "Aguarde terminarem.", "_retry": 20}
        os.makedirs(job_dir, exist_ok=True)
        inp = os.path.join(job_dir, "input.png")
        with open(inp, "wb") as f:
            f.write(png)
        row = dict(base, status="queued", stage="na fila", input_path=inp, image_w=info["w"], image_h=info["h"])
        if leader:
            row["dedup_of"] = leader["id"]
        D.insert_job(c, row)
        D.incr(c, "jobs_submitted_total", f"preset={opts['preset']},legacy={int(legacy)}")
        if leader:
            D.incr(c, "coalesced_total", f"preset={opts['preset']}")
        invalidate_plan()
    plan = get_plan(c, max_age=0)
    pos, eta = plan.get(leader["id"] if leader else job_id, (1, S.est_seconds.get(opts["preset"], 30.0)))
    body = {"job_id": job_id, "status": "queued", "position": int(pos), "eta_seconds": round(float(eta), 1)}
    if leader:
        body["deduplicated"] = True
    log.info("job enfileirado", extra=dict(job_id=job_id, preset=opts["preset"], position=pos,
                                           eta_s=round(eta, 1), bytes=len(data), coalesced=bool(leader),
                                           legacy=legacy, client=client[:10]))
    return 202, body


async def read_upload(up: UploadFile) -> bytes:
    data = bytearray()
    while True:
        chunk = await up.read(1 << 20)
        if not chunk:
            break
        data += chunk
        if len(data) > S.max_upload_bytes:
            M.REJECTED.labels("too_large").inc()
            raise HTTPException(413, f"A imagem é grande demais (max. {S.max_upload_bytes // 2**20} MB).")
    if not data:
        raise HTTPException(400, "Arquivo de imagem vazio.")
    return bytes(data)


async def create_job_common(request: Request, up: UploadFile, opts: dict, legacy: bool = False) -> tuple[int, dict]:
    key = client_key(request)
    ok, retry = rl_jobs.allow(key)
    if not ok:
        M.REJECTED.labels("rate_limit").inc()
        raise HTTPException(429, "Muitos envios em pouco tempo. Aguarde e tente novamente.",
                            headers={"Retry-After": str(max(1, int(retry + 0.999)))})
    ctype = (up.content_type or "").lower()
    if ctype and ctype not in ("image/jpeg", "image/jpg", "image/png", "image/pjpeg", "application/octet-stream"):
        M.REJECTED.labels("content_type").inc()
        raise HTTPException(400, f"Tipo de arquivo não suportado ({ctype}). Envie JPEG ou PNG.")
    data = await read_upload(up)
    code, body = await run_in_threadpool(_enqueue_sync, data, opts, key, legacy)
    if code == 429:
        raise HTTPException(429, body["detail"], headers={"Retry-After": str(body.get("_retry", 30))})
    if code >= 400:
        raise HTTPException(code, body["detail"])
    return code, body


# --------------------------------------------------------------------------------------------- esquemas (documentacao)
class HealthOut(BaseModel):
    status: str = Field(examples=["ok"], description="ok | loading | paused | degraded")
    model: str = Field(examples=["Hunyuan3D-2 Turbo (dit-v2-0-turbo + FlashVDM, paint-v2-0-turbo; alto: paint-v2-0)"])
    gpu: str = Field(examples=["NVIDIA GB10"])
    queue_length: int = Field(examples=[3])
    workers: int = Field(examples=[1], description="slots de execução prontos")
    presets: list[str] = Field(examples=[["rapido", "padrao", "alto"]])
    running: int | None = None
    max_queue: int | None = None


class JobCreatedOut(BaseModel):
    job_id: str = Field(examples=["385744908695454ba7a425f58bdc64fe"])
    status: str = Field(examples=["queued"], description="queued (ou done, se veio do cache)")
    position: int = Field(examples=[2], description="posição na fila (1 = próximo)")
    eta_seconds: float = Field(examples=[36.0], description="estimativa até o modelo ficar pronto (s)")
    cached: bool | None = None
    deduplicated: bool | None = None


class JobResultOut(BaseModel):
    glb_url: str = Field(examples=["/api/v1/jobs/385744908695454ba7a425f58bdc64fe/model.glb"])
    thumbnail_url: str = Field(examples=["/api/v1/jobs/385744908695454ba7a425f58bdc64fe/thumbnail.png"])
    stats: dict = Field(examples=[{"preset": "rapido", "seconds": 12.4, "faces": 10000, "glb_bytes": 1666096,
                                   "dims_m": [0.3, 0.289, 0.273], "gltf_extensions": []}])


class JobStateOut(BaseModel):
    job_id: str
    status: str = Field(examples=["running"], description="queued | running | done | error | cancelled")
    progress: int = Field(examples=[48], ge=0, le=100)
    stage: str = Field(examples=["texturizando (multivista)"])
    position: int = Field(examples=[0])
    eta_seconds: float = Field(examples=[6.5])
    error: str | None = None
    result: JobResultOut | None = None
    preset: str | None = None
    options: dict | None = None
    cached: bool | None = None
    timings: dict | None = None


class DetailOut(BaseModel):
    detail: str = Field(examples=["Fila do servidor cheia. Tente novamente em instantes."])


def _err(desc: str, example: str) -> dict:
    """Resposta de erro documentada no Swagger com exemplo proprio."""
    return {"description": desc, "model": DetailOut,
            "content": {"application/json": {"example": {"detail": example}}}}


# --------------------------------------------------------------------------------------------- rotas v1
@app.get("/api/v1/health", tags=["status"], summary="Estado do servidor, da fila e dos workers",
         responses={200: {"model": HealthOut}})
def health():
    c = conn()
    alive = D.alive_workers(c, S.worker_stale_s)
    qc = D.queue_counts(c)
    ready = [w for w in alive if w["state"] in ("ready", "busy")]
    slots = sum(int(w["slots"] or 0) for w in ready)
    gpu = next((w["gpu"] for w in alive if w["gpu"] and w["gpu"] != "?"), "desconhecida")
    presets = sorted({p for w in ready for p in (w["presets"] or "").split(",") if p}, key=S.presets.index) \
        if ready else list(S.presets)
    workers_detail = []
    for w in alive:
        info = json.loads(w["info_json"] or "{}")
        workers_detail.append(dict(id=w["id"], state=w["state"], slots=w["slots"], busy=w["busy"],
                                   gpu_mem=info.get("gpu_mem"), mem_available_gb=info.get("mem_available_gb"),
                                   mem_paused=info.get("mem_paused"), load_s=info.get("load_s"),
                                   jobs_done=info.get("jobs_done")))
    states = {w["state"] for w in alive}
    status = "ok" if ready else ("paused" if "paused" in states else "loading" if alive else "degraded")
    return {"status": status,
            "model": S.model_name, "gpu": gpu, "queue_length": qc["queued"], "workers": slots,
            "presets": presets, "running": qc["running"], "max_queue": S.max_queue, "version": __version__,
            "retention_days": S.retention_days, "worker_detail": workers_detail}


@app.post("/api/v1/jobs", status_code=202, tags=["jobs"], summary="Envia uma foto e cria um job de geração 3D",
          responses={202: {"description": "Job aceito (ou concluído na hora, se veio do cache)",
                           "model": JobCreatedOut},
                     400: _err("Imagem ou opções inválidas", "Preset inválido: 'ultra'. Use: rapido, padrao, alto."),
                     413: _err("Imagem > 15 MB", "A imagem é grande demais (max. 15 MB)."),
                     429: _err("Fila cheia ou limite de envios do cliente (cabeçalho Retry-After)",
                               "Fila do servidor cheia. Tente novamente em instantes.")})
async def create_job(request: Request,
                     image: UploadFile = File(..., description="Foto do objeto (JPEG ou PNG, até 15 MB)"),
                     options: str | None = Form(None, description='JSON: {"preset":"rapido|padrao|alto",'
                                                                  '"texture":true,"remove_background":true}')):
    opts = parse_options(options)
    code, body = await create_job_common(request, image, opts)
    return JSONResponse(body, status_code=code)


@app.get("/api/v1/jobs/{job_id}", tags=["jobs"], summary="Estado do job (fila, progresso, resultado)",
         responses={200: {"model": JobStateOut},
                    404: _err("Job não encontrado",
                              "Job não encontrado (ou já apagado pela política de retenção de 7 dias).")})
def get_job(job_id: str):
    c = conn()
    j = D.get_job(c, job_id)
    if j is None:
        raise HTTPException(404, "Job não encontrado (ou já apagado pela política de retenção de 7 dias).")
    return public_job(c, j)


def _file_of(job_id: str, kind: str) -> str:
    j = D.get_job(conn(), job_id)
    if j is None:
        raise HTTPException(404, "Job não encontrado.")
    if j["status"] != "done":
        raise HTTPException(409, "O modelo ainda não está pronto." if kind == "glb"
                            else "A miniatura ainda não está pronta.")
    p = j["glb_path"] if kind == "glb" else j["thumb_path"]
    if not p or not os.path.exists(p):
        raise HTTPException(404, "Arquivo não disponível (apagado pela política de retenção).")
    return p


@app.get("/api/v1/jobs/{job_id}/model.glb", tags=["jobs"], summary="Baixa o modelo GLB",
         response_class=FileResponse)
def get_glb(job_id: str):
    return FileResponse(_file_of(job_id, "glb"), media_type="model/gltf-binary", filename="model.glb",
                        headers={"Cache-Control": "private, max-age=86400"})


@app.get("/api/v1/jobs/{job_id}/thumbnail.png", tags=["jobs"], summary="Baixa a miniatura PNG",
         response_class=FileResponse)
def get_thumb(job_id: str):
    return FileResponse(_file_of(job_id, "thumb"), media_type="image/png",
                        headers={"Cache-Control": "private, max-age=86400"})


@app.delete("/api/v1/jobs/{job_id}", tags=["jobs"],
            summary="Cancela o job se ainda estiver na fila; se já terminou, apaga a foto e o modelo do servidor")
def delete_job(job_id: str):
    c = conn()
    st, j = D.cancel_job(c, job_id)
    if st == "missing":
        raise HTTPException(404, "Job não encontrado.")
    if st == "cancelled":
        invalidate_plan()
        if j and j.get("input_path"):
            try:
                os.remove(j["input_path"])
            except OSError:
                pass
        log.info("job cancelado", extra=dict(job_id=job_id))
        return {"job_id": job_id, "status": "cancelled"}
    if st == "running":
        raise HTTPException(409, "Job em execução; não pode ser cancelado.")
    # done/error/cancelled: o usuario pediu para apagar os dados do servidor
    if j and j["job_dir"] and os.path.isdir(j["job_dir"]):
        shutil.rmtree(j["job_dir"], ignore_errors=True)
    D.delete_job_row(c, job_id)
    D.incr(c, "user_deleted_total", "")
    return {"job_id": job_id, "status": "deleted"}


@app.get("/api/v1/queue", tags=["status"], summary="Resumo anônimo da fila (para painel/operação)")
def queue_summary():
    c = conn()
    plan = get_plan(c, max_age=0)
    rows = c.execute("SELECT id, status, preset, progress, stage, created_at, started_at FROM jobs "
                     "WHERE status IN ('queued','running') AND dedup_of IS NULL ORDER BY status DESC, score").fetchall()
    now = time.time()
    items = [dict(job=r["id"][:8], status=r["status"], preset=r["preset"], progress=r["progress"], stage=r["stage"],
                  position=plan.get(r["id"], (0, 0))[0], eta_s=round(plan.get(r["id"], (0, 0.0))[1], 1),
                  age_s=round(now - r["created_at"], 1)) for r in rows]
    return {"queue_length": sum(1 for i in items if i["status"] == "queued"),
            "running": sum(1 for i in items if i["status"] == "running"), "slots": total_slots(c), "items": items}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(M.render(), media_type="text/plain; version=0.0.4; charset=utf-8")


# --------------------------------------------------------------------------------------------- legado 2025
@app.get("/", include_in_schema=False)
def legacy_index():
    return PlainTextResponse("Servidor de geração 3D do CERISE rodando! API: /api/v1 (documentação em /docs). "
                             "Compatibilidade 2025: envie uma requisição POST multipart para este endpoint.")


@app.post("/", tags=["legado"], summary="Endpoint do app Android de 2025 (síncrono: devolve o GLB na resposta)",
          responses={200: {"content": {"model/gltf-binary": {}}, "description": "GLB gerado"}})
async def legacy_upload(request: Request):
    """Compatibilidade com o app Android 2025 (`MainActivity.kt`): multipart com as fotos (`front`, `left`, `back`,
    `right`) + campo `metadata` (JSON). Usa a foto `front` (o modelo e de imagem unica), cria um job normal na fila
    (preset `GEN3D_LEGACY_PRESET`, ou `metadata.preset`) e segura a conexao ate o GLB ficar pronto (o app de 2025
    espera ate 5 min). Diferente de 2025, a espera e assincrona: nao prende uma thread por cliente."""
    form = await request.form(max_files=8, max_fields=16)
    files = [(k, v) for k, v in form.multi_items() if isinstance(v, StarletteUploadFile)]
    if not files and "metadata" not in form:
        return JSONResponse({"mensagem": "Nenhum arquivo ou metadado encontrado na requisição"}, status_code=400)
    meta = {}
    if "metadata" in form:
        try:
            meta = json.loads(str(form["metadata"]))
        except json.JSONDecodeError as e:
            return JSONResponse({"mensagem": "Erro ao decodificar metadados JSON", "erro": str(e)}, status_code=400)
    if not files:
        return JSONResponse({"mensagem": "Nenhuma imagem enviada"}, status_code=400)
    order = {"front": 0, "image": 1}
    files.sort(key=lambda kv: order.get(kv[0], 9))
    up = files[0][1]
    preset = meta.get("preset", S.legacy_preset) if isinstance(meta, dict) else S.legacy_preset
    if preset not in S.presets:
        preset = S.legacy_preset
    opts = {"preset": preset, "texture": True, "remove_background": True}
    try:
        _, body = await create_job_common(request, up, opts, legacy=True)
    except HTTPException as e:
        return JSONResponse({"mensagem": e.detail}, status_code=e.status_code, headers=e.headers)
    job_id = body["job_id"]
    t0 = time.time()
    while time.time() - t0 < S.legacy_timeout_s:
        j = await run_in_threadpool(D.get_job, conn(), job_id)
        if j is None:
            break
        if j["status"] == "done":
            return FileResponse(j["glb_path"], media_type="model/gltf-binary", filename="objeto_ajustado.glb",
                                headers={"X-Job-Id": job_id})
        if j["status"] in ("error", "cancelled"):
            return JSONResponse({"mensagem": "Erro no servidor ao gerar o modelo", "erro": j["error"],
                                 "job_id": job_id}, status_code=500)
        await asyncio.sleep(0.5)
    return JSONResponse({"mensagem": "Tempo de espera esgotado; o job continua na fila",
                         "job_id": job_id, "status_url": f"/api/v1/jobs/{job_id}"}, status_code=504,
                        headers={"X-Job-Id": job_id})

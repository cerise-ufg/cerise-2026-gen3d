"""Testes automatizados da API/fila com o motor simulado (FakeEngine, sem GPU).

Rodar: cd server && python -m pytest -v tests/
"""
from __future__ import annotations

import io
import json
import os
import threading
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from cerise_gen3d_server import api as A
from cerise_gen3d_server import db as D
from cerise_gen3d_server.common import TokenBucket, normalize_image
from cerise_gen3d_server.config import settings as S
from cerise_gen3d_server.worker import Worker

PAUSE = os.path.join(S.data_dir, "PAUSE")


def png_bytes(seed: int, size=(96, 96), alpha=True) -> bytes:
    im = Image.new("RGBA" if alpha else "RGB", size, (seed * 37 % 255, seed * 91 % 255, seed * 53 % 255, 255))
    for x in range(size[0] // 8, size[0] * 5 // 8):
        for y in range(size[1] // 5, size[1] * 3 // 4):
            im.putpixel((x, y), (255 - seed % 255, 30, 30, 255) if alpha else (255 - seed % 255, 30, 30))
    b = io.BytesIO()
    im.save(b, format="PNG")
    return b.getvalue()


_seed = [100]


def new_img() -> bytes:
    _seed[0] += 1
    return png_bytes(_seed[0])


def hdr(client="10.0.0.1"):
    return {"X-Forwarded-For": client}


@pytest.fixture(scope="module")
def client():
    with TestClient(A.app) as c:
        w = Worker()
        t = threading.Thread(target=w.run, daemon=True)
        t.start()
        for _ in range(100):
            if c.get("/api/v1/health").json()["status"] == "ok":
                break
            time.sleep(0.1)
        c.worker = w
        yield c
        w.stop.set()
        t.join(5)


def submit(c, data, opts=None, client="10.0.0.1", name="foto.png", ctype="image/png"):
    files = {"image": (name, data, ctype)}
    form = {"options": json.dumps(opts)} if opts is not None else {}
    return c.post("/api/v1/jobs", files=files, data=form, headers=hdr(client))


def wait_done(c, job_id, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = c.get(f"/api/v1/jobs/{job_id}").json()
        if j["status"] in ("done", "error", "cancelled"):
            return j
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} nao terminou: {j}")


def pause():
    open(PAUSE, "w").close()


def resume():
    if os.path.exists(PAUSE):
        os.remove(PAUSE)


# ------------------------------------------------------------------------------------------- contrato
def test_health_contract(client):
    h = client.get("/api/v1/health").json()
    assert h["status"] == "ok"
    for k, t in (("model", str), ("gpu", str), ("queue_length", int), ("workers", int), ("presets", list)):
        assert isinstance(h[k], t), k
    assert h["presets"] == ["rapido", "padrao", "alto"]
    assert h["workers"] == 1


def test_job_lifecycle_and_downloads(client):
    r = submit(client, new_img(), {"preset": "rapido", "texture": True, "remove_background": True})
    assert r.status_code == 202, r.text
    b = r.json()
    assert set(b) >= {"job_id", "status", "position", "eta_seconds"} and b["status"] == "queued"
    j = wait_done(client, b["job_id"])
    assert j["status"] == "done" and j["progress"] == 100 and j["error"] is None
    assert j["result"]["glb_url"] == f"/api/v1/jobs/{b['job_id']}/model.glb"
    g = client.get(j["result"]["glb_url"])
    assert g.status_code == 200 and g.headers["content-type"] == "model/gltf-binary" and g.content[:4] == b"glTF"
    t = client.get(j["result"]["thumbnail_url"])
    assert t.status_code == 200 and t.headers["content-type"] == "image/png"
    assert j["result"]["stats"]["triangles"] > 0
    # a foto enviada e apagada apos o processamento (privacidade)
    row = D.get_job(A.conn(), b["job_id"])
    assert not os.path.exists(row["input_path"])


def test_progress_and_stage_while_running(client):
    seen = set()
    r = submit(client, new_img(), {"preset": "alto"})
    jid = r.json()["job_id"]
    t0 = time.time()
    while time.time() - t0 < 20:
        j = client.get(f"/api/v1/jobs/{jid}").json()
        if j["status"] == "running":
            seen.add((j["stage"], j["progress"]))
        if j["status"] == "done":
            break
        time.sleep(0.03)
    assert len(seen) >= 3, seen  # varias etapas com progresso crescente
    assert sorted(p for _, p in seen) == [p for _, p in sorted(seen, key=lambda x: x[1])]


# ------------------------------------------------------------------------------------------- validacao
def test_invalid_uploads(client):
    assert submit(client, b"isto nao e imagem", {"preset": "rapido"}).status_code == 400
    assert submit(client, new_img(), {"preset": "ultra"}).status_code == 400
    r = client.post("/api/v1/jobs", files={"image": ("a.png", new_img(), "image/png")}, data={"options": "{oops"},
                    headers=hdr())
    assert r.status_code == 400 and "JSON" in r.json()["detail"]
    assert submit(client, new_img(), {"preset": "rapido", "texture": "sim"}).status_code == 400
    assert submit(client, png_bytes(1, size=(32, 32)), {"preset": "rapido"}).status_code == 400  # pequena demais
    assert submit(client, b"GIF89a....", {"preset": "rapido"}, ctype="image/gif").status_code == 400
    big = b"\xff\xd8" + os.urandom(16 * 1024 * 1024)
    assert submit(client, big, {"preset": "rapido"}, ctype="image/jpeg").status_code == 413
    assert client.get("/api/v1/jobs/naoexiste").status_code == 404


def test_exif_orientation_and_metadata_removed():
    im = Image.new("RGB", (200, 100), (10, 200, 10))
    exif = Image.Exif()
    exif[0x0112] = 6  # rotacao 90 graus
    exif[0x8825] = {2: (16.0, 40.0, 0.0)}  # bloco GPS
    b = io.BytesIO()
    im.save(b, format="JPEG", exif=exif.tobytes())
    png, info = normalize_image(b.getvalue(), 50_000_000, 64, 2048)
    out = Image.open(io.BytesIO(png))
    assert out.size == (100, 200)  # girou conforme EXIF
    assert not out.info.get("exif") and len(out.getexif()) == 0


# ------------------------------------------------------------------------------------------- cache
def test_cache_hit_is_instant(client):
    img = new_img()
    opts = {"preset": "rapido"}
    j1 = wait_done(client, submit(client, img, opts).json()["job_id"])
    t0 = time.perf_counter()
    r = submit(client, img, opts, client="10.0.0.99")
    dt = time.perf_counter() - t0
    assert r.status_code == 202 and r.json()["status"] == "done" and r.json()["cached"] is True
    assert dt < 1.0
    j2 = client.get(f"/api/v1/jobs/{r.json()['job_id']}").json()
    assert j2["status"] == "done" and j2["result"]["stats"]["cached"] is True
    assert client.get(j2["result"]["glb_url"]).content == client.get(j1["result"]["glb_url"]).content
    # opcoes diferentes -> nao usa o cache
    r3 = submit(client, img, {"preset": "padrao"})
    assert r3.json()["status"] == "queued"
    wait_done(client, r3.json()["job_id"])


def test_coalescing_identical_inflight(client):
    pause()
    try:
        img = new_img()
        a = submit(client, img, {"preset": "rapido"}, client="10.1.1.1").json()
        b = submit(client, img, {"preset": "rapido"}, client="10.1.1.2").json()
        same = submit(client, img, {"preset": "rapido"}, client="10.1.1.1").json()
        assert b.get("deduplicated") and b["job_id"] != a["job_id"]
        assert same["job_id"] == a["job_id"]  # reenvio idempotente do mesmo cliente
        assert client.get(f"/api/v1/jobs/{b['job_id']}").json()["stage"] == "aguardando pedido idêntico"
    finally:
        resume()
    ja, jb = wait_done(client, a["job_id"]), wait_done(client, b["job_id"])
    assert ja["status"] == jb["status"] == "done"
    assert jb["result"]["stats"].get("deduplicated_from") == a["job_id"]


# ------------------------------------------------------------------------------------------- fila
def test_priority_order_by_preset(client):
    pause()
    try:
        time.sleep(0.3)
        ids = {}
        for p, ip in (("alto", "10.2.0.1"), ("padrao", "10.2.0.2"), ("rapido", "10.2.0.3")):
            ids[p] = submit(client, new_img(), {"preset": p}, client=ip).json()["job_id"]
        pos = {p: client.get(f"/api/v1/jobs/{i}").json()["position"] for p, i in ids.items()}
        assert pos == {"rapido": 1, "padrao": 2, "alto": 3}, pos
        etas = {p: client.get(f"/api/v1/jobs/{i}").json()["eta_seconds"] for p, i in ids.items()}
        assert etas["rapido"] < etas["padrao"] < etas["alto"]
    finally:
        resume()
    done = {p: wait_done(client, i) for p, i in ids.items()}
    st = {p: done[p]["timings"]["started_at"] for p in done}
    assert st["rapido"] < st["padrao"] < st["alto"]


def test_backpressure_queue_full(client):
    pause()
    old = S.max_queue
    S.max_queue = 3
    try:
        time.sleep(0.3)
        codes = [submit(client, new_img(), {"preset": "rapido"}, client=f"10.3.0.{i}") for i in range(5)]
        assert [r.status_code for r in codes] == [202, 202, 202, 429, 429]
        assert "Retry-After" in codes[3].headers and "cheia" in codes[3].json()["detail"]
        assert client.get("/api/v1/health").json()["queue_length"] == 3
    finally:
        S.max_queue = old
        resume()
    for r in codes[:3]:
        wait_done(client, r.json()["job_id"])


def test_per_client_cap_and_rate_limit(client):
    pause()
    old = S.max_queued_per_client
    S.max_queued_per_client = 2
    try:
        rs = [submit(client, new_img(), {"preset": "rapido"}, client="10.4.0.1") for _ in range(3)]
        assert [r.status_code for r in rs] == [202, 202, 429]
    finally:
        S.max_queued_per_client = old
        resume()
    for r in rs[:2]:
        wait_done(client, r.json()["job_id"])
    old_rl = A.rl_jobs
    A.rl_jobs = TokenBucket(rate_per_min=1, burst=2)
    try:
        rs = [submit(client, new_img(), {"preset": "rapido"}, client="10.4.0.2") for _ in range(3)]
        assert [r.status_code for r in rs] == [202, 202, 429]
        assert int(rs[2].headers["Retry-After"]) >= 1
        # outro cliente nao e afetado
        assert submit(client, new_img(), {"preset": "rapido"}, client="10.4.0.3").status_code == 202
    finally:
        A.rl_jobs = old_rl


def test_cancel_and_delete(client):
    pause()
    try:
        jid = submit(client, new_img(), {"preset": "rapido"}).json()["job_id"]
        r = client.delete(f"/api/v1/jobs/{jid}")
        assert r.status_code == 200 and r.json()["status"] == "cancelled"
        j = client.get(f"/api/v1/jobs/{jid}").json()
        assert j["status"] == "cancelled" and j["stage"] == "cancelado"
        assert client.get(f"/api/v1/jobs/{jid}/model.glb").status_code == 409
    finally:
        resume()
    jid2 = submit(client, new_img(), {"preset": "rapido"}).json()["job_id"]
    wait_done(client, jid2)
    r = client.delete(f"/api/v1/jobs/{jid2}")  # ja concluido: apaga os dados do servidor
    assert r.status_code == 200 and r.json()["status"] == "deleted"
    assert client.get(f"/api/v1/jobs/{jid2}").status_code == 404
    assert client.delete("/api/v1/jobs/naoexiste").status_code == 404


def test_engine_error_reported(client):
    poison = png_bytes(7, size=(77, 77))
    j = wait_done(client, submit(client, poison, {"preset": "rapido"}).json()["job_id"])
    assert j["status"] == "error" and "falha" in j["error"] and j["result"] is None


def test_texture_false_option(client):
    j = wait_done(client, submit(client, new_img(), {"preset": "rapido", "texture": False}).json()["job_id"])
    assert j["status"] == "done" and j["options"]["texture"] is False


# ------------------------------------------------------------------------------------------- robustez
def test_restart_recovery_requeues_running_job(client):
    c = A.conn()
    pause()
    try:
        jid = submit(client, new_img(), {"preset": "rapido"}).json()["job_id"]
        # simula um worker que morreu no meio do job
        c.execute("UPDATE jobs SET status='running', worker_id='worker-morto', started_at=?, attempts=1 WHERE id=?",
                  (time.time(), jid))
        res = D.requeue_worker_jobs(c, "worker-morto", S.max_attempts, "reiniciado")
        assert res == [(jid, "queued")]
        # sem mais tentativas -> erro explicito
        c.execute("UPDATE jobs SET status='running', worker_id='worker-morto', attempts=2 WHERE id=?", (jid,))
        assert D.requeue_worker_jobs(c, "worker-morto", 2, "reiniciado") == [(jid, "error")]
        jid2 = submit(client, new_img(), {"preset": "rapido"}).json()["job_id"]
        c.execute("UPDATE jobs SET status='running', worker_id='worker-morto', attempts=0 WHERE id=?", (jid2,))
        D.upsert_worker(c, dict(id="worker-morto", slots=1, busy=1, presets="rapido", state="busy", gpu="x",
                                model="x", started_at=time.time() - 999, heartbeat=time.time() - 999,
                                info_json="{}"))
        out = A.janitor_once()  # heartbeat velho -> job volta para a fila
        assert out["requeued"] == 1
    finally:
        resume()
    assert wait_done(client, jid2)["status"] == "done"
    c.execute("DELETE FROM workers WHERE id='worker-morto'")


def test_retention_ttl_and_queue_timeout(client):
    c = A.conn()
    old_dir = os.path.join(S.jobs_dir, "velho")
    os.makedirs(old_dir, exist_ok=True)
    open(os.path.join(old_dir, "model.glb"), "wb").write(b"glTF")
    t_old = time.time() - 8 * 86400
    D.insert_job(c, dict(id="velho", status="done", preset="rapido", score=t_old, created_at=t_old,
                         job_dir=old_dir, glb_path=os.path.join(old_dir, "model.glb")))
    pause()
    try:
        t_q = time.time() - 2 * 3600
        D.insert_job(c, dict(id="esquecido", status="queued", preset="rapido", score=t_q, created_at=t_q,
                             job_dir=os.path.join(S.jobs_dir, "esquecido")))
        out = A.janitor_once()
    finally:
        resume()
    assert out["expired"] >= 1 and out["queue_timeout"] >= 1
    assert D.get_job(c, "velho") is None and not os.path.exists(old_dir)
    assert D.get_job(c, "esquecido")["status"] == "error"


# ------------------------------------------------------------------------------------------- legado 2025
def test_legacy_endpoint_2025(client):
    meta = json.dumps({"front": "IMG_0001.jpg", "view_type": "single_view"})
    b = io.BytesIO()
    Image.open(io.BytesIO(new_img())).convert("RGB").save(b, format="JPEG")
    r = client.post("/", files={"front": ("IMG_0001.jpg", b.getvalue(), "image/jpeg")},
                    data={"metadata": meta, "view_type": "single_view"}, headers=hdr("10.5.0.1"))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "model/gltf-binary" and r.content[:4] == b"glTF"
    assert "objeto_ajustado.glb" in r.headers["content-disposition"]
    assert client.get(f"/api/v1/jobs/{r.headers['x-job-id']}").json()["status"] == "done"
    r = client.post("/", data={}, headers=hdr("10.5.0.1"))
    assert r.status_code == 400 and "mensagem" in r.json()
    assert client.get("/").status_code == 200


def test_metrics_endpoint(client):
    m = client.get("/metrics").text
    for name in ("gen3d_queue_length", "gen3d_http_requests_total", "gen3d_workers_alive",
                 "gen3d_job_run_seconds_bucket", "gen3d_jobs_total", "gen3d_cache_hits_total"):
        assert name in m, name


def test_docs_and_openapi(client):
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json").json()
    for p in ("/api/v1/health", "/api/v1/jobs", "/api/v1/jobs/{job_id}", "/api/v1/jobs/{job_id}/model.glb"):
        assert p in spec["paths"], p

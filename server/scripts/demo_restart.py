"""Demonstracao de robustez (roda no host do Spark, so com a biblioteca padrao):
1) envia 4 jobs; 2) com um job em execucao, MATA o worker (docker kill = queda abrupta) e reinicia a API;
3) mostra que nenhum job se perdeu: o job interrompido volta para a fila e todos terminam depois que o worker volta.

Uso: python3 scripts/demo_restart.py <pasta_de_imagens> [url]
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid

BASE = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8095"
T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:6.1f}s] {msg}", flush=True)


def post_job(path, preset="rapido"):
    b = "----cerise" + uuid.uuid4().hex
    data = open(path, "rb").read()
    ctype = "image/png" if path.endswith(".png") else "image/jpeg"
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{os.path.basename(path)}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode() + data + \
        (f"\r\n--{b}\r\nContent-Disposition: form-data; name=\"options\"\r\n\r\n"
         f"{json.dumps({'preset': preset})}\r\n--{b}--\r\n").encode()
    req = urllib.request.Request(BASE + "/api/v1/jobs", data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def get(path):
    try:
        return json.loads(urllib.request.urlopen(BASE + path, timeout=10).read())
    except Exception as e:  # noqa: BLE001
        return {"erro": str(e)}


def show(ids):
    for i in ids:
        j = get(f"/api/v1/jobs/{i}")
        if "erro" in j:
            log(f"  {i[:8]}  (API indisponivel: {j['erro'][:50]})")
        else:
            log(f"  {i[:8]}  {j['status']:9s} {j['progress']:3d}% {j['stage']:26s} pos={j['position']}")


def sh(cmd):
    log("$ " + cmd)
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if out.stdout.strip():
        log("  " + out.stdout.strip().replace("\n", " | "))


def main():
    folder = sys.argv[1]
    imgs = sorted(os.path.join(folder, f) for f in os.listdir(folder))[44:48]
    ids = []
    for p in imgs:
        r = post_job(p)
        ids.append(r["job_id"])
        log(f"POST /api/v1/jobs {os.path.basename(p)[:30]:30s} -> {r['status']} pos={r['position']} "
            f"eta={r['eta_seconds']}s id={r['job_id'][:8]}")
    while get(f"/api/v1/jobs/{ids[0]}").get("progress", 0) < 20:
        time.sleep(0.5)
    show(ids)
    log("== queda abrupta do worker no meio do job (SIGKILL) e restart da API")
    sh("sudo docker kill cerise26_gen3d_worker1")
    sh("sudo docker restart cerise26_gen3d_api")
    time.sleep(3)
    show(ids)
    sh("sudo docker start cerise26_gen3d_worker1")
    log("== worker recarregando o modelo; jobs continuam no SQLite")
    last = None
    while True:
        h = get("/api/v1/health")
        st = h.get("status")
        if st != last:
            log(f"GET /api/v1/health -> status={st} workers={h.get('workers')} fila={h.get('queue_length')}")
            last = st
        js = [get(f"/api/v1/jobs/{i}") for i in ids]
        if all(j.get("status") in ("done", "error") for j in js):
            break
        time.sleep(3)
    log("== resultado final")
    for i in ids:
        j = get(f"/api/v1/jobs/{i}")
        t = j["timings"]
        log(f"  {i[:8]}  {j['status']:5s} fila={t['queue_s']}s exec={t['run_s']}s "
            f"glb={j['result']['stats']['glb_bytes'] if j['result'] else '-'} bytes")
    sh("sudo docker logs cerise26_gen3d_worker1 2>&1 | grep -E 'recuperados|modelo carregado' | cut -c1-230")


if __name__ == "__main__":
    main()

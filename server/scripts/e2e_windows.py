"""Teste ponta a ponta a partir do Windows, pelo encaminhamento LOCAL de SSH (nada exposto na internet):

    ssh -N -L 127.0.0.1:18095:localhost:8095 spark-bridge      (em outro terminal)
    python scripts/e2e_windows.py --base http://127.0.0.1:18095 --photo <foto.jpg> --out <pasta>

Passos: health -> envia foto real (preset padrao) -> acompanha fila/progresso -> baixa GLB e miniatura -> confere o GLB
(cabecalho glTF 2.0, sem Draco/meshopt/KTX2, escala) -> reenvia (cache) -> endpoint legado de 2025 -> erros de validacao.
So usa `requests` (ja instalado no Windows).
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glb_check  # noqa: E402  (mesma pasta: caixa no mundo, formato real da textura)


def glb_info(path: str) -> dict:
    with open(path, "rb") as f:
        b = f.read()
    magic, ver, length = struct.unpack("<4sII", b[:12])
    clen, ctype = struct.unpack("<II", b[12:20])
    js = json.loads(b[20:20 + clen])
    tris = 0
    for m in js.get("meshes", []):
        for p in m["primitives"]:
            if "indices" in p:
                tris += js["accessors"][p["indices"]]["count"] // 3
    pos = [js["accessors"][p["attributes"]["POSITION"]] for m in js.get("meshes", []) for p in m["primitives"]]
    return dict(magic=magic.decode(), version=ver, bytes=length, triangles=tris,
                extensionsUsed=js.get("extensionsUsed", []), images=[i.get("mimeType") for i in js.get("images", [])],
                materials=len(js.get("materials", [])), pos_min=pos[0].get("min") if pos else None,
                pos_max=pos[0].get("max") if pos else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:18095")
    ap.add_argument("--photo", required=True)
    ap.add_argument("--preset", default="padrao")
    ap.add_argument("--out", default="e2e_out")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    B = a.base.rstrip("/")
    s = requests.Session()
    print(f"$ GET {B}/api/v1/health")
    h = s.get(B + "/api/v1/health", timeout=10).json()
    print(json.dumps({k: h[k] for k in ("status", "model", "gpu", "queue_length", "workers", "presets")},
                     ensure_ascii=False))
    print(f"\n$ POST {B}/api/v1/jobs  (foto {os.path.basename(a.photo)}, {os.path.getsize(a.photo)} bytes, "
          f"preset {a.preset})")
    t0 = time.time()
    with open(a.photo, "rb") as f:
        r = s.post(B + "/api/v1/jobs", files={"image": (os.path.basename(a.photo), f, "image/jpeg")},
                   data={"options": json.dumps({"preset": a.preset, "texture": True, "remove_background": True})},
                   timeout=60)
    print(r.status_code, r.text)
    job = r.json()["job_id"]
    last = None
    while True:
        j = s.get(f"{B}/api/v1/jobs/{job}", timeout=10).json()
        line = f"  t={time.time() - t0:5.1f}s  {j['status']:8s} {j['progress']:3d}%  {j['stage']:28s} " \
               f"pos={j['position']} eta={j['eta_seconds']}s"
        if line.split("t=")[1][7:] != last:
            print(line)
            last = line.split("t=")[1][7:]
        if j["status"] in ("done", "error", "cancelled"):
            break
        time.sleep(1.0)
    if j["status"] != "done":
        print("ERRO:", j.get("error"))
        sys.exit(1)
    st = j["result"]["stats"]
    print(f"\nconcluido em {time.time() - t0:.1f} s (fila {j['timings']['queue_s']} s, geracao {st['seconds']} s); "
          f"faces={st['faces']} glb={st['glb_bytes']} bytes textura={st.get('texture_mime')} "
          f"dims_m={[round(x, 3) for x in st['dims_m']]}")
    for url, name in ((j["result"]["glb_url"], "model.glb"), (j["result"]["thumbnail_url"], "thumbnail.png")):
        t1 = time.time()
        g = s.get(B + url, timeout=120)
        p = os.path.join(a.out, name)
        with open(p, "wb") as f:
            f.write(g.content)
        print(f"$ GET {url} -> HTTP {g.status_code} {g.headers.get('content-type')} {len(g.content)} bytes "
              f"em {time.time() - t1:.2f} s -> {p}")
    gi = glb_info(os.path.join(a.out, "model.glb"))
    assert gi["magic"] == "glTF" and gi["version"] == 2
    bad = {"KHR_draco_mesh_compression", "EXT_meshopt_compression", "KHR_texture_basisu"} & set(gi["extensionsUsed"])
    gc = glb_check.check(os.path.join(a.out, "model.glb"))
    print(f"GLB: glTF {gc['gltf_version']} binario, {gc['triangles']} triangulos, baseColorTexture="
          f"{gc['baseColorTexture']}, textura {gc['images'][0]['real']} {gc['images'][0]['w']}x{gc['images'][0]['h']}"
          f" | sem Draco/meshopt/KTX2: {not bad}")
    print(f"     caixa no mundo: {gc['dims_m']} m (maior {gc['max_dim_m']} m), y_min={gc['y_min_m']}, "
          f"centro_xz={gc['centro_xz_m']}")

    print("\n$ POST /api/v1/jobs (mesma foto e opcoes de novo -> cache)")
    t1 = time.time()
    with open(a.photo, "rb") as f:
        r2 = s.post(B + "/api/v1/jobs", files={"image": (os.path.basename(a.photo), f, "image/jpeg")},
                    data={"options": json.dumps({"preset": a.preset, "texture": True, "remove_background": True})},
                    timeout=60)
    cache_ms = (time.time() - t1) * 1000
    print(r2.status_code, r2.text, f"({cache_ms:.0f} ms)")

    print("\n$ POST /  (endpoint legado do app Android 2025: 'front' + metadata, resposta = GLB)")
    t1 = time.time()
    meta = json.dumps({"front": "IMG_front.jpg", "view_type": "single_view"})
    with open(a.photo, "rb") as f:
        data = f.read()
    # 1 pixel diferente no nome nao muda o hash; usa o preset rapido do legado (outro hash -> gera de verdade)
    r3 = s.post(B + "/", files={"front": ("IMG_front.jpg", data, "image/jpeg")},
                data={"metadata": meta, "view_type": "single_view"}, timeout=310)
    legacy_s = time.time() - t1
    p = os.path.join(a.out, "legado_objeto_ajustado.glb")
    with open(p, "wb") as f:
        f.write(r3.content)
    print(f"HTTP {r3.status_code} {r3.headers.get('content-type')} {r3.headers.get('content-disposition')} "
          f"{len(r3.content)} bytes em {time.time() - t1:.1f} s (job {r3.headers.get('x-job-id')}) -> {p}")
    gl = glb_check.check(p) if r3.status_code == 200 else {}
    if gl:
        print(f"GLB legado: glTF {gl['gltf_version']}, {gl['triangles']} triangulos, textura {gl['images'][0]['real']}"
              f" {gl['images'][0]['w']}x{gl['images'][0]['h']}, maior dimensao {gl['max_dim_m']} m, "
              f"y_min={gl['y_min_m']}")

    print("\n$ erros de validacao")
    e1 = s.post(B + "/api/v1/jobs", files={"image": ("nota.txt", b"nao sou imagem", "text/plain")}, timeout=30)
    print("  texto no lugar da foto ->", e1.status_code, e1.json())
    e2 = s.post(B + "/api/v1/jobs", files={"image": ("a.jpg", data, "image/jpeg")},
                data={"options": json.dumps({"preset": "ultra"})}, timeout=30)
    print("  preset invalido        ->", e2.status_code, e2.json())
    e3 = s.get(B + "/api/v1/jobs/inexistente", timeout=10)
    print("  job inexistente        ->", e3.status_code, e3.json())
    with open(os.path.join(a.out, "e2e_resultado.json"), "w", encoding="utf-8") as f:
        json.dump(dict(job=j, glb=gi, glb_check=gc, cache=r2.json(), cache_ms=round(cache_ms, 1),
                       legado=dict(status=r3.status_code, bytes=len(r3.content), job=r3.headers.get("x-job-id"),
                                   seconds=round(legacy_s, 2), glb_check=gl),
                       erros=dict(texto=e1.status_code, preset=e2.status_code, inexistente=e3.status_code)),
                  f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()

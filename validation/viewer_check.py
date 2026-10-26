"""Confere se os GLB finais carregam no <model-viewer> e no three.js (GLTFLoader + Draco/meshopt), em Chromium
headless (Playwright, WebGL por SwiftShader). Serve os arquivos so em 127.0.0.1 dentro do container.

python viewer_check.py --out /workspace/evidencias/viewer --glbs a.glb b.glb ...
"""
import argparse
import functools
import http.server
import json
import os
import shutil
import socketserver
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NM = os.environ.get("NODE_MODULES", "/opt/gltf-tools/node_modules")


def build_site(site):
    os.makedirs(os.path.join(site, "lib"), exist_ok=True)
    shutil.copy(os.path.join(HERE, "viewer", "index.html"), site)
    shutil.copy(os.path.join(NM, "@google/model-viewer/dist/model-viewer.min.js"), os.path.join(site, "lib"))
    for f in os.listdir(os.path.join(NM, "three/build")):
        if f.endswith(".js"):
            shutil.copy(os.path.join(NM, "three/build", f), os.path.join(site, "lib"))
    for cand in ("meshoptimizer/meshopt_decoder.js", "meshoptimizer/meshopt_decoder.cjs"):
        if os.path.exists(os.path.join(NM, cand)):
            shutil.copy(os.path.join(NM, cand), os.path.join(site, "lib", "meshopt_decoder.js"))
            break
    dst = os.path.join(site, "lib", "jsm")
    if not os.path.exists(dst):
        shutil.copytree(os.path.join(NM, "three/examples/jsm"), dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glbs", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=8095)
    a = ap.parse_args()
    site = "/tmp/viewer_site"
    build_site(site)
    os.makedirs(os.path.join(site, "m"), exist_ok=True)
    names = []
    for i, g in enumerate(a.glbs):
        n = f"{i:02d}_" + "_".join(g.strip("/").split("/")[-3:]).replace(".glb", "") + ".glb"
        shutil.copy(g, os.path.join(site, "m", n))
        names.append((g, n))
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=site)
    handler.log_message = lambda *x: None
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", a.port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    from playwright.sync_api import sync_playwright
    os.makedirs(a.out, exist_ok=True)
    report = []
    with sync_playwright() as p:
        br = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        page = br.new_page(viewport={"width": 900, "height": 590})
        logs = []
        page.on("console", lambda m: logs.append(m.text))
        for g, n in names:
            page.goto(f"http://127.0.0.1:{a.port}/index.html?src=m/{n}")
            t0 = time.time()
            mv = th = None
            while time.time() - t0 < 90:
                mv = page.evaluate("window.__mv || null")
                th = page.evaluate("window.__three || null")
                if mv and th:
                    break
                time.sleep(0.5)
            time.sleep(2.5)  # deixa o render estabilizar
            shot = os.path.join(a.out, n.replace(".glb", ".png"))
            page.screenshot(path=shot)
            report.append(dict(glb=g, model_viewer=mv, three=th, screenshot=shot, size_bytes=os.path.getsize(g),
                               console=[x for x in logs if "rror" in x][-3:]))
            logs.clear()
            print(json.dumps(report[-1], ensure_ascii=False))
        br.close()
    httpd.shutdown()
    json.dump(report, open(os.path.join(a.out, "viewer_report.json"), "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()

"""Reproducao MEDIDA do servidor de 2025 (CERISE-AR/server.py) com o modelo REAL.

O servidor de 2025 era um Flask (servidor de desenvolvimento, threaded) que recebia as fotos, fazia `time.sleep(67)`
e devolvia sempre o mesmo `objeto_ajustado.glb`. Aqui o `sleep(67)` e trocado pela chamada SINCRONA ao modelo real
(Gen3DPipeline, carregado uma vez no processo), mantendo o resto da arquitetura de 2025:
  * Flask dev server, uma thread por conexao, sem fila, sem limite de concorrencia;
  * a resposta HTTP so volta quando o GLB fica pronto (conexao presa durante toda a geracao);
  * arquivos de saida em caminho FIXO (`/tmp/saida/model.glb`, como o `objeto_ajustado.glb` de 2025);
  * sem validacao de imagem, sem cache, sem persistencia, sem metricas.

Modos (BASELINE_MODE):
  nolock  chamadas concorrentes entram direto no modelo (o que o codigo de 2025 faria com o modelo real);
  lock    um Lock global serializa a GPU (a correcao minima "obvia"); as demais conexoes ficam esperando presas.

Executar (no container cerise26_gen3d_server, com GPU): python baseline_2025/server_2025_real.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time

from flask import Flask, jsonify, request, send_file
from werkzeug.utils import secure_filename

sys.path.insert(0, os.environ.get("GEN3D_PIPELINE_DIR", "/opt/gen3d/pipeline"))
from gen3d_pipeline import DEFAULT_PRESETS, Gen3DPipeline  # noqa: E402

MODE = os.environ.get("BASELINE_MODE", "nolock")
PRESET = os.environ.get("BASELINE_PRESET", "rapido")
PORT = int(os.environ.get("PORT", "8096"))

app = Flask(__name__)
UPLOAD_FOLDER = "/tmp/uploads"
OUT_DIR = "/tmp/saida"  # caminho fixo, como em 2025
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

t0 = time.time()
print(f"[2025-real] carregando o modelo (preset {PRESET}, modo {MODE})...", flush=True)
PIPE = Gen3DPipeline(presets={PRESET: DEFAULT_PRESETS[PRESET]}, warmup=True)
print(f"[2025-real] modelo pronto em {time.time() - t0:.1f} s", flush=True)
LOCK = threading.Lock()
ACTIVE = {"n": 0, "max": 0}
ACTIVE_LOCK = threading.Lock()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/", methods=["POST"])
def upload_files():
    if not request.files and "metadata" not in request.form:
        return jsonify({"mensagem": "Nenhum arquivo ou metadado encontrado na requisição"}), 400
    saved = []
    for key, file in request.files.items():
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            saved.append((key, filepath))
    if "metadata" in request.form:
        try:
            json.loads(request.form["metadata"])
        except json.JSONDecodeError as e:
            return jsonify({"mensagem": "Erro ao decodificar metadados JSON", "erro": str(e)}), 400
    if not saved:
        return jsonify({"mensagem": "Nenhuma imagem válida"}), 400
    saved.sort(key=lambda kv: 0 if kv[0] == "front" else 1)
    img = saved[0][1]
    with ACTIVE_LOCK:
        ACTIVE["n"] += 1
        ACTIVE["max"] = max(ACTIVE["max"], ACTIVE["n"])
    t = time.time()
    try:
        if MODE == "lock":
            with LOCK:
                out = PIPE.generate(img, OUT_DIR, PRESET)
        else:
            out = PIPE.generate(img, OUT_DIR, PRESET)
        with open(out["glb_path"], "rb") as f:
            sha_gerado = hashlib.sha256(f.read()).hexdigest()
    except Exception as e:  # noqa: BLE001
        print(f"[2025-real] ERRO: {type(e).__name__}: {e}", flush=True)
        return jsonify({"mensagem": "Erro no processamento", "erro": f"{type(e).__name__}: {str(e)[:300]}"}), 500
    finally:
        with ACTIVE_LOCK:
            ACTIVE["n"] -= 1
    resp = send_file(out["glb_path"], mimetype="model/gltf-binary", as_attachment=True,
                     download_name="objeto_ajustado.glb")
    resp.headers["X-Server-Seconds"] = f"{time.time() - t:.3f}"
    resp.headers["X-GLB-SHA-Gerado"] = sha_gerado
    resp.headers["X-Max-Concorrencia"] = str(ACTIVE["max"])
    return resp


@app.route("/")
def index():
    return "Servidor Flask para upload de imagens rodando! Envie uma requisição POST para este endpoint."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)

"""Gera ~/cerise2026/gen3d/READY.json a partir das medicoes dos presets (results/presets) e do pytest (A4)."""
import glob
import json
import os
import statistics as st
import subprocess
import time

ROOT = os.environ.get("GEN3D_ROOT", "/workspace")
PRES = os.path.join(ROOT, "results", "presets")
presets_cfg = json.load(open(os.path.join(ROOT, "pipeline", "presets.json")))


def summarize(name):
    p = os.path.join(PRES, f"preset_{name}", "summary.json")
    if not os.path.exists(p):
        return None
    s = json.load(open(p))
    ok = [o for o in s["objects"].values() if o.get("ok")]
    gso = [o for o in ok if not o.get("real_photo")]
    real = [o for o in ok if o.get("real_photo")]

    def stat(lst, k):
        v = [o[k] for o in lst if o.get(k) is not None]
        return None if not v else dict(mediana=round(st.median(v), 2), min=round(min(v), 2), max=round(max(v), 2), n=len(v))
    stages = {}
    for o in ok:
        for k, v in o["times"].items():
            stages.setdefault(k, []).append(v)
    return dict(
        objetos_ok=len(ok), objetos_total=len(s["objects"]),
        tempo_total_s=stat(ok, "total_s"), tempo_total_s_gso=stat(gso, "total_s"), tempo_total_s_fotos_reais=stat(real, "total_s"),
        tempo_mediano_por_etapa_s={k: round(st.median(v), 3) for k, v in stages.items()},
        faces=stat(ok, "faces"), glb_final_bytes=stat(ok, "size_bytes"), pico_gpu_gb=stat(ok, "peak_alloc_gb"),
        loadavg_inicio=s.get("loadavg_start"), loadavg_fim=s.get("loadavg_end"))


loads = {}
for f in glob.glob(os.path.join(PRES, "pipeline_load_*.json")):
    loads[os.path.basename(f)[len("pipeline_load_"):-5]] = json.load(open(f))
pytest = {}
for f in glob.glob(os.path.join(ROOT, "results", "a4_pytest", "junit_*.xml")):
    txt = open(f).read(4000)
    i = txt.find("<testsuite ")
    pytest[os.path.basename(f)] = txt[i:txt.find(">", i) + 1]

img = subprocess.run(["bash", "-c", "cat /workspace/logs/image_id.txt 2>/dev/null"], capture_output=True, text=True).stdout.strip()
ready = dict(
    frente="gen3d", gerado_em=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    imagem_docker="cerise26_gen3d:latest", imagem_id=img or None,
    modelo=dict(forma="tencent/Hunyuan3D-2 hunyuan3d-dit-v2-0-turbo + FlashVDM (VAE turbo)",
                textura="tencent/Hunyuan3D-2 hunyuan3d-paint-v2-0-turbo (+ hunyuan3d-delight-v2-0); preset 'alto' usa hunyuan3d-paint-v2-0",
                licenca="Tencent Hunyuan 3D 2.0 Community License (nao vale na UE/Reino Unido/Coreia do Sul)"),
    modulo=dict(caminho_no_spark="~/cerise2026/gen3d/pipeline/gen3d_pipeline.py",
                caminho_na_imagem="/opt/gen3d/pipeline/gen3d_pipeline.py",
                classe="Gen3DPipeline",
                metodo="generate(image_path, out_dir, preset='padrao') -> {glb_path, thumb_path, stats{times, total_s, faces, size_bytes, geometry, peak_gpu_gb, gltf_extensions}}"),
    requisitos_do_app=dict(
        glb_sem_compressao_geometrica=True,
        motivo="o <model-viewer> embutido (offline) e o ViroReact nao tem decodificadores Draco/meshopt/KTX2",
        texturas="JPEG (glTF-Transform), lado <= mobile_texture do preset",
        escala="metros; maior dimensao = target_size_m (0,30 m); objeto apoiado em y=0 e centralizado em x/z (o app normaliza para ~35 cm)"),
    como_instanciar=dict(
        docker_run=("sudo docker run -d --name cerise26_gen3d_srv --gpus all --ipc=host "
                    "-v ~/cerise2026/hf_cache:/root/.cache/huggingface "
                    "-v ~/cerise2026/gen3d/hy3dgen_models:/opt/gen3d/hy3dgen_models "
                    "-p 127.0.0.1:8095:8095 cerise26_gen3d:latest <comando do servidor>"),
        python=("import sys; sys.path.insert(0, '/opt/gen3d/pipeline'); from gen3d_pipeline import Gen3DPipeline; "
                "pipe = Gen3DPipeline(); out = pipe.generate('/caminho/foto.jpg', '/tmp/saida', preset='padrao')"),
        observacoes=["HY3DGEN_MODELS=/opt/gen3d/hy3dgen_models (arvore de links para o cache HF + UNet do paint convertido para .bin)",
                     "carregar so os presets necessarios: Gen3DPipeline(presets={k: DEFAULT_PRESETS[k] for k in ['rapido','padrao']}) evita carregar o paint completo do 'alto'",
                     "a imagem limita o alocador a 24 GB (gpu_cap_gb); conferir free -g (>= 10 GB livres alem do modelo) antes de subir, pois a producao (vLLM) divide a memoria unificada",
                     "nao expor a porta fora do loopback: exposicao publica e decisao pendente do Eduardo"]),
    carga_medida=loads,
    presets={k: dict(parametros=v, medido=summarize(k)) for k, v in presets_cfg.items()},
    pytest=pytest,
)
out = os.path.join(ROOT, "READY.json")
json.dump(ready, open(out, "w"), indent=1, ensure_ascii=False)
print(json.dumps(ready, indent=1, ensure_ascii=False)[:3000])

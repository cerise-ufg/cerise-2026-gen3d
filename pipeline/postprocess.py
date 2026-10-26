"""Pos-processamento do GLB para o celular (AR):

1. orientacao/assentamento (ideia do central_z.py de 2025, corrigida): centraliza em X e Z, coloca o ponto mais
   baixo em Y = 0 (glTF e Y-para-cima; o script de 2025 deslocava Z pelo centro de Y por engano);
2. escala metrica: maior dimensao = `target_size_m` (padrao 0,30 m);
3. reducao/recompressao da textura (JPEG, glTF-Transform) -> tamanho final. Por requisito do app (model-viewer
   offline + ViroReact sem decodificadores), o GLB entregue NAO usa Draco, meshopt nem KTX2 (method="none");
   Draco/meshopt existem aqui so para a comparacao do benchmark A3;
4. miniatura PNG (render com nvdiffrast, mesmo renderizador do benchmark).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

import numpy as np
import trimesh

GLTF_TOOLS = os.environ.get("GLTF_TOOLS", "/opt/gltf-tools/node_modules/.bin")


def ground_center_scale(glb_in, glb_out, target_size_m=0.30, front_yaw_deg=0.0):
    """Centraliza X/Z, apoia no chao (min Y = 0) e escala para a maior dimensao = target_size_m (metros)."""
    scene = trimesh.load(glb_in, force="scene", process=False)
    if front_yaw_deg:
        R = trimesh.transformations.rotation_matrix(np.radians(front_yaw_deg), [0, 1, 0])
        scene.apply_transform(R)
    lo, hi = scene.bounds
    ext = float((hi - lo).max())
    s = target_size_m / ext if ext > 0 else 1.0
    T = np.eye(4)
    T[:3, :3] *= s
    T[:3, 3] = -np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2]) * s
    scene.apply_transform(T)
    scene.export(glb_out)
    lo2, hi2 = scene.bounds
    return dict(scale=s, bounds_min=[float(x) for x in lo2], bounds_max=[float(x) for x in hi2],
                dims_m=[float(x) for x in (hi2 - lo2)])


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"falha: {' '.join(cmd)}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return r.stdout


def compress(glb_in, glb_out, method="draco", texture_size=1024, jpeg_quality=85):
    """glTF-Transform: redimensiona texturas, converte para JPEG e comprime a geometria (draco|meshopt|none)."""
    gt = os.path.join(GLTF_TOOLS, "gltf-transform")
    tmp = glb_out + ".tmp.glb"
    shutil.copy(glb_in, tmp)
    _run([gt, "resize", tmp, tmp, "--width", str(texture_size), "--height", str(texture_size)])
    # --formats "*": na glTF-Transform 4.5 o padrao do comando jpeg e --formats jpeg (so recomprime texturas que ja
    # sao JPEG); sem isso a textura PNG do Hunyuan3D passava sem conversao (constatado no teste ponta a ponta do
    # servidor, 26/10). A imagem cerise26_gen3d:latest ainda tem a versao antiga; o servidor usa a sua propria rotina.
    _run([gt, "jpeg", tmp, tmp, "--formats", "*", "--quality", str(jpeg_quality)])
    if method == "draco":
        _run([gt, "draco", tmp, glb_out, "--method", "edgebreaker"])
    elif method == "meshopt":
        _run([gt, "meshopt", tmp, glb_out, "--level", "medium"])
    else:
        shutil.copy(tmp, glb_out)
    os.remove(tmp)
    return os.path.getsize(glb_out)


FORBIDDEN_EXTENSIONS = ("KHR_draco_mesh_compression", "EXT_meshopt_compression", "KHR_texture_basisu",
                        "KHR_meshopt_compression")


def extensions_used(glb_path):
    """Lista extensionsUsed do GLB e o mimeType das imagens (requisito do app: sem Draco/meshopt/KTX2)."""
    from pygltflib import GLTF2
    g = GLTF2().load(glb_path)
    return dict(extensions=list(g.extensionsUsed or []), image_mime=sorted({im.mimeType or "" for im in g.images}))


def validate(glb_path):
    """Khronos glTF-Validator (npm). Retorna dict com numErrors/numWarnings."""
    js = (
        "const v=require('gltf-validator');const fs=require('fs');"
        f"const a=new Uint8Array(fs.readFileSync('{glb_path}'));"
        "v.validateBytes(a,{maxIssues:50}).then(r=>{console.log(JSON.stringify({numErrors:r.issues.numErrors,"
        "numWarnings:r.issues.numWarnings,numInfos:r.issues.numInfos,"
        "messages:r.issues.messages.slice(0,8).map(m=>m.code+': '+m.message)}))}).catch(e=>{console.log("
        "JSON.stringify({error:String(e)}))});"
    )
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True,
                         cwd=os.path.dirname(GLTF_TOOLS.rstrip("/").replace("/.bin", "")) or None,
                         env=dict(os.environ, NODE_PATH=GLTF_TOOLS.replace("/.bin", "")))
    try:
        return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return {"error": out.stderr[-500:]}


def thumbnail(glb_path, png_path, size=512, azim=30.0, elev=20.0):
    from render_utils import crop_to_content, load_parts, normalize_parts, render
    parts = load_parts(glb_path)
    normalize_parts(parts, 1.0)
    im, _ = render(parts, azim=azim, elev=elev, dist=2.6, fovy=30, res=int(size * 1.5))
    rgba, _ = crop_to_content(im, out=size, fill=0.85)
    rgba.save(png_path)
    return png_path

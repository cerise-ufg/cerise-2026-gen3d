#!/bin/bash
# lista arquivos (e tamanhos) de subpastas dos repositorios HF dos modelos
for rp in "tencent/Hunyuan3D-2 hunyuan3d-dit-v2-0" "tencent/Hunyuan3D-2 hunyuan3d-dit-v2-0-turbo" "tencent/Hunyuan3D-2 hunyuan3d-vae-v2-0-turbo" \
          "tencent/Hunyuan3D-2 hunyuan3d-paint-v2-0" "tencent/Hunyuan3D-2 hunyuan3d-paint-v2-0-turbo" "tencent/Hunyuan3D-2 hunyuan3d-delight-v2-0" \
          "tencent/Hunyuan3D-2mini hunyuan3d-dit-v2-mini-turbo" "tencent/Hunyuan3D-2mini hunyuan3d-vae-v2-mini-turbo" \
          "tencent/Hunyuan3D-2.1 hunyuan3d-dit-v2-1" "tencent/Hunyuan3D-2.1 hunyuan3d-paintpbr-v2-1" "tencent/Hunyuan3D-2.1 hunyuan3d-vae-v2-1"; do
  set -- $rp
  echo "== $1/$2"
  curl -s "https://huggingface.co/api/models/$1/tree/main/$2?recursive=true" | python3 -c 'import sys,json
for f in json.load(sys.stdin):
    if f.get("type")=="file": print("  ", f["path"], round(f.get("size",0)/1e6,1), "MB")'
done

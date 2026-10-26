#!/bin/bash
# Clona os repositorios oficiais dos modelos avaliados (somente leitura / referencia)
set -x
mkdir -p ~/cerise2026/gen3d/third_party && cd ~/cerise2026/gen3d/third_party
which git
clone() { [ -d "$2" ] || git clone --depth 1 "$1" "$2"; (cd "$2" && echo "$2 $(git rev-parse HEAD)") ; }
clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2.git Hunyuan3D-2
clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1.git Hunyuan3D-2.1
clone https://github.com/VAST-AI-Research/TripoSR.git TripoSR
clone https://github.com/Stability-AI/stable-fast-3d.git stable-fast-3d
clone https://github.com/TencentARC/InstantMesh.git InstantMesh
clone https://github.com/microsoft/TRELLIS.git TRELLIS
clone https://github.com/microsoft/TRELLIS.2.git TRELLIS.2
clone https://github.com/NVlabs/nvdiffrast.git nvdiffrast
clone https://github.com/tatsy/torchmcubes.git torchmcubes
du -sh *
# acesso aos pesos no HF (sem login): HEAD do arquivo de config
for r in tencent/Hunyuan3D-2 tencent/Hunyuan3D-2mini tencent/Hunyuan3D-2.1 stabilityai/TripoSR stabilityai/stable-fast-3d stabilityai/stable-point-aware-3d TencentARC/InstantMesh microsoft/TRELLIS-image-large microsoft/TRELLIS.2-4B; do
  code=$(curl -s -o /dev/null -w '%{http_code}' -L "https://huggingface.co/api/models/$r")
  gated=$(curl -s -L "https://huggingface.co/api/models/$r" | python3 -c 'import sys,json; d=json.load(sys.stdin); print("gated=",d.get("gated"), "license=", (d.get("cardData") or {}).get("license"), (d.get("cardData") or {}).get("license_name"))' 2>/dev/null)
  echo "$r http=$code $gated"
done

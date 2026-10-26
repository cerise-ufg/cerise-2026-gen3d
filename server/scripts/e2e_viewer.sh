#!/usr/bin/env bash
# Confere os GLBs baixados no teste ponta a ponta (copiados para results/e2e/): Khronos glTF-Validator e
# carregamento no <model-viewer> e no three.js (Chromium headless, SwiftShader) dentro do container de
# desenvolvimento cerise26_gen3d_dev (tem Playwright e /opt/gltf-tools). Nada e aberto na tela fisica do Spark.
# Uso (no Spark): bash scripts/e2e_viewer.sh model_padrao.glb legado_objeto_ajustado.glb
set -u
cd "$(dirname "$0")/.."
E=results/e2e
WAS_RUNNING=$(sudo docker inspect -f '{{.State.Running}}' cerise26_gen3d_dev 2>/dev/null)
[ "$WAS_RUNNING" = "true" ] || sudo docker start cerise26_gen3d_dev >/dev/null
ARGS=""; for g in "$@"; do ARGS="$ARGS /workspace/server/$E/$g"; done
echo "== glTF-Validator (Khronos)"
sudo docker exec cerise26_gen3d_dev bash -c "cd /opt/gltf-tools && for f in $ARGS; do node -e '
const v=require(\"gltf-validator\"); const fs=require(\"fs\"); const f=process.argv[1];
v.validateBytes(new Uint8Array(fs.readFileSync(f))).then(r=>{const i=r.issues;
console.log(f.split(\"/\").pop()+\": erros=\"+i.numErrors+\" avisos=\"+i.numWarnings+\" infos=\"+i.numInfos+\" | \"+
  r.info.totalTriangleCount+\" triangulos, \"+r.info.materialCount+\" material, imagens: \"+
  (r.info.resources||[]).filter(x=>x.pointer.startsWith(\"/images\")).map(x=>x.mimeType+\" \"+x.image.width+\"x\"+x.image.height).join(\", \"));
fs.writeFileSync(f.replace(/\\.glb$/,\".validator.json\"), JSON.stringify(r,null,1));});' \$f 2>&1 | grep -v -i -e experimental -e trace-warnings; done"
echo "== <model-viewer> + three.js (Chromium headless)"
sudo docker exec cerise26_gen3d_dev bash -c "cd /workspace/validation && python viewer_check.py --port 8197 --out /workspace/server/$E/viewer --glbs $ARGS" 2>&1 | grep -v -i warn
[ "$WAS_RUNNING" = "true" ] || sudo docker stop cerise26_gen3d_dev >/dev/null

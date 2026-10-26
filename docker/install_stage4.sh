#!/bin/bash
# Etapa 4: ferramentas de pos-processamento/validacao de GLB (Node: gltf-transform, gltfpack (wasm), gltf-validator)
# e Playwright (Chromium headless) para conferir o carregamento no three.js / <model-viewer>.
set -x
export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq nodejs npm > /dev/null
node --version; npm --version
mkdir -p /opt/gltf-tools && cd /opt/gltf-tools
npm init -y > /dev/null
nice -n 19 npm install --no-audit --no-fund @gltf-transform/cli@4 gltfpack gltf-validator @google/model-viewer three > /tmp/npm.log 2>&1; echo "NPM_RC=$?"
tail -5 /tmp/npm.log
ls node_modules/.bin | tr '\n' ' '; echo
./node_modules/.bin/gltf-transform --version
nice -n 19 pip install --no-cache-dir playwright pygltflib; echo "PW_PIP_RC=$?"
nice -n 19 python -m playwright install --with-deps chromium > /tmp/pw.log 2>&1; echo "PW_RC=$?"
tail -3 /tmp/pw.log

#!/bin/bash
# reinstala as ferramentas glTF com o Node 22 (binarios opcionais do sharp para linux-arm64)
set -e
export PATH=/usr/local/bin:$PATH
mkdir -p /opt/gltf-tools && cd /opt/gltf-tools
rm -rf node_modules package-lock.json
[ -f package.json ] || npm init -y > /dev/null
nice -n 19 npm install --no-audit --no-fund --include=optional @gltf-transform/cli@4 gltfpack gltf-validator @google/model-viewer three > /tmp/npm2.log 2>&1 || (tail -20 /tmp/npm2.log; exit 1)
./node_modules/.bin/gltf-transform --version
node -e "require('sharp'); console.log('sharp ok')"

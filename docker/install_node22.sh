#!/bin/bash
# Node 22 LTS oficial (nodejs.org, linux-arm64): o sharp usado pelo glTF-Transform exige Node >= 20
set -e
V=v22.11.0
cd /opt
[ -d node-$V-linux-arm64 ] || (curl -sL https://nodejs.org/dist/$V/node-$V-linux-arm64.tar.xz | tar xJ)
ln -sf /opt/node-$V-linux-arm64/bin/node /usr/local/bin/node
ln -sf /opt/node-$V-linux-arm64/bin/npm /usr/local/bin/npm
ln -sf /opt/node-$V-linux-arm64/bin/npx /usr/local/bin/npx
hash -r
/usr/local/bin/node --version
cd /opt/gltf-tools && /usr/local/bin/npm rebuild sharp > /dev/null 2>&1 || true
/opt/gltf-tools/node_modules/.bin/gltf-transform --version

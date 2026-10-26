#!/usr/bin/env bash
# Renderiza os diagramas de arquitetura (graphviz em container descartavel; nada instalado no host).
cd "$(dirname "$0")"
sudo docker run --rm --name cerise26_gen3d_graphviz -v "$PWD:/w" cerise26_gen3d_server:latest bash -c '
  apt-get update -qq >/dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq graphviz fonts-dejavu-core >/dev/null 2>&1
  cd /w && dot -V && for f in arquitetura_2025 arquitetura_2026; do dot -Tpng -Gdpi=150 $f.dot -o $f.png; dot -Tsvg $f.dot -o $f.svg; done
  chown '"$(id -u):$(id -g)"' *.png *.svg; ls -la *.png *.svg'

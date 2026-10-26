#!/usr/bin/env bash
# pytest do servidor com o codigo atual montado (motor simulado, sem GPU)
cd ~/cerise2026/gen3d/server
sudo docker run --rm \
  -v "$PWD/cerise_gen3d_server:/opt/gen3d/server/cerise_gen3d_server:ro" \
  -v "$PWD/tests:/opt/gen3d/server/tests:ro" \
  -e PYTHONDONTWRITEBYTECODE=1 -e COLUMNS=110 \
  cerise26_gen3d_server:latest python -m pytest -v -p no:cacheprovider tests/ 2>&1 | grep -v -e '^$' | sed -n '/test session starts/,$p'

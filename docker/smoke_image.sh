#!/bin/bash
# (host) teste rapido da imagem cerise26_gen3d:latest (sem carregar modelos)
echo "$ sudo docker images cerise26_gen3d"
sudo docker images cerise26_gen3d --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}\t{{.CreatedSince}}'
echo
echo "$ sudo docker run --rm --gpus all cerise26_gen3d:latest <verificacoes>"
sudo docker run --rm --gpus all --ipc=host cerise26_gen3d:latest bash -c '
python -c "import torch, custom_rasterizer, nvdiffrast.torch, pymeshlab, fast_simplification; print(\"torch\", torch.__version__, \"cuda\", torch.cuda.is_available(), torch.cuda.get_device_name(0), \"cap\", torch.cuda.get_device_capability(0))"
python -c "import sys; sys.path.insert(0, \"pipeline\"); import gen3d_pipeline as g; print(\"gen3d_pipeline ok; presets:\", list(g.DEFAULT_PRESETS))"
node --version; /opt/gltf-tools/node_modules/.bin/gltf-transform --version 2>/dev/null | tail -1
ls /opt/gen3d'
sudo docker inspect cerise26_gen3d:latest --format '{{.Id}}' > ~/cerise2026/gen3d/logs/image_id.txt
cat ~/cerise2026/gen3d/logs/image_id.txt

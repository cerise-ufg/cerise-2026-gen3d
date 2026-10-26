#!/bin/bash
# Etapa 2b: libs que o pymeshlab (Qt) exige + torchmcubes via scikit-build-core
set -x
export MAX_JOBS=4 CMAKE_BUILD_PARALLEL_LEVEL=4
export TORCH_CUDA_ARCH_LIST="12.1"
export DEBIAN_FRONTEND=noninteractive
TP=${TP:-/workspace/third_party}
apt-get install -y -qq libharfbuzz0b libfontconfig1 libfreetype6 libxkbcommon0 libdbus-1-3 libx11-6 libxcb1 libgomp1 libtbb12 > /dev/null
python - <<'EOF'
import os, glob, subprocess
import importlib.util
spec = importlib.util.find_spec("pymeshlab")
d = os.path.dirname(spec.origin)
miss = set()
for so in glob.glob(d + "/**/*.so*", recursive=True):
    out = subprocess.run(["ldd", so], capture_output=True, text=True).stdout
    for l in out.splitlines():
        if "not found" in l: miss.add(l.strip())
print("MISSING:", sorted(miss)[:30])
EOF
python -c "import pymeshlab; ms=pymeshlab.MeshSet(); print('pymeshlab OK')"
nice -n 19 pip install --no-cache-dir scikit-build-core cmake
cd $TP/torchmcubes && nice -n 19 pip install --no-build-isolation --no-cache-dir . ; echo "TORCHMCUBES_RC=$?"
cd / && python -c "import torch, torchmcubes; from torchmcubes import marching_cubes; v,f = marching_cubes(torch.randn(32,32,32).cuda(), 0.0); print('torchmcubes OK', v.shape, f.shape)"

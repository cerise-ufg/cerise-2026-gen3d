#!/bin/bash
# Verifica disponibilidade (sem instalar) das dependencias binarias do TRELLIS para linux aarch64 / cp312
cd /tmp
for p in spconv-cu126 spconv-cu124 spconv-cu121 spconv-cu120 spconv cumm-cu126 xformers kaolin torchsparse pyvista pymeshfix igraph vtk; do
  out=$(pip download --no-deps --only-binary=:all: --platform manylinux2014_aarch64 --platform manylinux_2_28_aarch64 --platform manylinux_2_17_aarch64 --python-version 312 -d /tmp/pdl "$p" 2>&1 | tail -1)
  echo "$p :: $out"
done
ls /tmp/pdl 2>/dev/null
rm -rf /tmp/pdl
grep -n "BACKEND\|ATTN" /workspace/third_party/TRELLIS/trellis/modules/sparse/__init__.py | head -20
grep -rn "^import kaolin\|from kaolin" /workspace/third_party/TRELLIS/trellis | head
grep -rn "dinov2\|torch.hub" /workspace/third_party/TRELLIS/trellis/pipelines/trellis_image_to_3d.py | head -5

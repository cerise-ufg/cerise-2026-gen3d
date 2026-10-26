#!/bin/bash
cd ~/cerise2026/gen3d/third_party
for r in Hunyuan3D-2 Hunyuan3D-2.1 TripoSR stable-fast-3d InstantMesh TRELLIS TRELLIS.2; do
  echo "=================== $r"
  grep -n -i -E "vram|gb |memory|second|seconds| s on|A100|H100|H20|4090|licen|params|parameters|billion| [0-9.]+B " $r/README.md | grep -v -i "badge\|shields" | head -25
  head -3 $r/LICENSE* 2>/dev/null | head -3
done

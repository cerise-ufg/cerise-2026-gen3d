#!/bin/bash
for r in sudo-ai/zero123plus-v1.2 TencentARC/InstantMesh facebook/dinov2-giant facebook/dino-vitb16 microsoft/TRELLIS-image-large microsoft/TRELLIS.2-4B; do
  echo "== $r"
  curl -s "https://huggingface.co/api/models/$r/tree/main?recursive=true" | python3 -c 'import sys,json
for f in json.load(sys.stdin):
    if f.get("type")=="file": print("  ", f["path"], round(f.get("size",0)/1e6,1), "MB")'
done
for r in facebook/dinov3-vitl16-pretrain-lvd1689m briaai/RMBG-2.0 ZhengPeng7/BiRefNet; do
  curl -s "https://huggingface.co/api/models/$r" | python3 -c 'import sys,json; d=json.load(sys.stdin); print("'$r'", "gated=", d.get("gated"), (d.get("cardData") or {}).get("license"))'
done
grep -rn "dinov3\|RMBG\|BiRefNet\|from_pretrained(" ~/cerise2026/gen3d/third_party/TRELLIS.2/trellis2/pipelines/*.py 2>/dev/null | head -12

"""Teste rapido do pos-processamento sobre um GLB ja gerado: assentar/escala, compressao e validacao Khronos."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import postprocess as PP  # noqa: E402

src = sys.argv[1]
od = sys.argv[2]
os.makedirs(od, exist_ok=True)
g = os.path.join(od, "grounded.glb")
info = PP.ground_center_scale(src, g, 0.30)
res = {"entrada_bytes": os.path.getsize(src), "assentado_bytes": os.path.getsize(g), "geo": info}
for m in ("none", "draco", "meshopt"):
    for tex in (2048, 1024, 512):
        o = os.path.join(od, f"model_{m}_{tex}.glb")
        PP.compress(g, o, method=m, texture_size=tex)
        v = PP.validate(o)
        res[f"{m}_{tex}"] = {"bytes": os.path.getsize(o), "erros": v.get("numErrors"), "avisos": v.get("numWarnings"),
                             "msgs": v.get("messages", [])[:3], "err": v.get("error")}
print(json.dumps(res, indent=1))
json.dump(res, open(os.path.join(od, "postprocess_sizes.json"), "w"), indent=1)

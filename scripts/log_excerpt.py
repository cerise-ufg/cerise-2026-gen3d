"""Extrai as linhas relevantes de um log de run_model.py (carga, aquecimento, por objeto, FIM) e encurta as etapas."""
import ast
import re
import sys

keep = re.compile(r"limite de memoria|carga do modelo|aquecimento|ok=(True|False)|FIM|^\[[a-z0-9_]+\] |^=== ")
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    line = line.rstrip()
    if not keep.search(line):
        continue
    m = re.search(r"etapas=(\{.*\})", line)
    if m:
        try:
            d = ast.literal_eval(m.group(1))
            top = sorted(d.items(), key=lambda kv: -kv[1])[:4]
            line = line[: m.start()] + "etapas(top4)=" + ", ".join(f"{k}={v:.1f}" for k, v in top)
        except Exception:  # noqa: BLE001
            pass
    line = line.replace("Transformers_Age_of_Extinction_Mega_1Step_Bumblebee_Figure", "Transformers_Bumblebee")
    print(line)

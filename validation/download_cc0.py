"""Baixa (miniatura de 1024 px) as fotos reais escolhidas (CC0 / dominio publico, Wikimedia Commons) e grava
fontes.json com titulo, licenca, autor e pagina de origem."""
import json
import os
import sys
import urllib.request

UA = {"User-Agent": "CERISE-UFG-research/1.0 (relatorio academico; contato via GitHub EduardoCaixeta)"}
CHOSEN = {
    "cc0_teapot": "File:Teapot MET DP164196.jpg",
    "cc0_donkey": "File:Donkey figurine MET DP101825.jpg",
    "cc0_rooster": "File:Rooster figurine MET DP101869.jpg",
    "cc0_cat": "File:Crouching Cat Figurine MET DT226229.jpg",
    "cc0_duck": "File:Duck Donuts Rubber Duck.jpg",
    "cc0_angular_teapot": "File:Angular teapot by Walter Keeler, V&A London.jpg",
}
out_dir = sys.argv[1] if len(sys.argv) > 1 else "real"
os.makedirs(out_dir, exist_ok=True)
cands = {}
for f in ("cc0_candidates.json", "cc0_candidates2.json"):
    if os.path.exists(f):
        for c in json.load(open(f, encoding="utf-8")):
            cands[c["title"]] = c
fontes = {}
for name, title in CHOSEN.items():
    c = cands[title]
    dst = os.path.join(out_dir, name + ".jpg")
    with urllib.request.urlopen(urllib.request.Request(c["thumb"], headers=UA), timeout=60) as r:
        open(dst, "wb").write(r.read())
    fontes[name] = dict(arquivo=name + ".jpg", titulo=title, licenca=c["license"], autor=c["artist"],
                        pagina=c["page"], url_baixada=c["thumb"])
    print(name, os.path.getsize(dst), c["license"])
json.dump(fontes, open(os.path.join(out_dir, "fontes.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)

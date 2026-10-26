"""Reconstroi summary.json de uma rodada interrompida a partir dos stats.json por objeto (marca partial=True).
python make_summary.py <dir_da_tag> [--load-s X]"""
import argparse
import json
import os

ap = argparse.ArgumentParser()
ap.add_argument("tagdir")
ap.add_argument("--load-s", type=float, default=None)
ap.add_argument("--note", default="rodada interrompida; so objetos concluidos")
a = ap.parse_args()
objs = {}
for o in sorted(os.listdir(a.tagdir)):
    p = os.path.join(a.tagdir, o, "stats.json")
    if os.path.isdir(os.path.join(a.tagdir, o)) and os.path.exists(p):
        objs[o] = json.load(open(p))
tag = os.path.basename(a.tagdir.rstrip("/"))
s = dict(tag=tag, partial=True, note=a.note, load_s=a.load_s, objects=objs)
json.dump(s, open(os.path.join(a.tagdir, "summary.json"), "w"), indent=1)
print(tag, len(objs), "objetos:", list(objs))

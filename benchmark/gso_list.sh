#!/bin/bash
# Lista os modelos da colecao GoogleResearch (Google Scanned Objects) no Gazebo Fuel
OUT=~/cerise2026/gen3d/data/gso_names.txt
mkdir -p ~/cerise2026/gen3d/data
: > $OUT
for p in $(seq 1 12); do
  curl -s "https://fuel.gazebosim.org/1.0/GoogleResearch/models?per_page=100&page=$p" | \
    python3 -c 'import sys,json
d=json.load(sys.stdin)
for m in d: print(m["name"], m.get("filesize",0), ",".join(m.get("categories") or []), sep="\t")' >> $OUT 2>/dev/null
done
wc -l $OUT
grep -iE 'schleich|mug|shoe|boot|figure|teapot|bus|dino|horse|clock|panda|mario|elephant|truck|lamp|plant|kettle|camera|turtle|bear|chair|rhino|lion|toaster|backpack|sneaker' $OUT | awk -F'\t' '{print $1" ("$2")"}' | head -200 | tr '\n' ';'

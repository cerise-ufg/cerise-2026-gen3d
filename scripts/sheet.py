"""Folha de contato simples: python sheet.py saida.png arquivo1 arquivo2 ... (ou um glob)."""
import glob
import sys

from PIL import Image

out = sys.argv[1]
fs = []
for a in sys.argv[2:]:
    fs += sorted(glob.glob(a)) or [a]
W = 300
cols = min(6, len(fs))
rows = (len(fs) + cols - 1) // cols
s = Image.new("RGB", (W * cols, W * rows), "white")
for i, f in enumerate(fs):
    im = Image.open(f).convert("RGB")
    im.thumbnail((W, W))
    s.paste(im, ((i % cols) * W, (i // cols) * W))
s.save(out)
print(out, len(fs))

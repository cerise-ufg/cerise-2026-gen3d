"""Montagem em grade de imagens (ex.: capturas do visualizador): python montage.py saida.png --cols 2 --width 560 a.png b.png"""
import argparse
import glob

from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("files", nargs="+")
ap.add_argument("--cols", type=int, default=2)
ap.add_argument("--width", type=int, default=560)
ap.add_argument("--pad", type=int, default=8)
a = ap.parse_args()
fs = []
for f in a.files:
    fs += sorted(glob.glob(f)) or [f]
ims = [Image.open(f).convert("RGB") for f in fs]
ims = [im.resize((a.width, int(im.height * a.width / im.width)), Image.LANCZOS) for im in ims]
h = max(im.height for im in ims)
rows = (len(ims) + a.cols - 1) // a.cols
W = a.cols * a.width + (a.cols + 1) * a.pad
H = rows * h + (rows + 1) * a.pad
out = Image.new("RGB", (W, H), (252, 252, 251))
for i, im in enumerate(ims):
    r, c = divmod(i, a.cols)
    out.paste(im, (a.pad + c * (a.width + a.pad), a.pad + r * (h + a.pad)))
out.save(a.out)
print(a.out, len(ims))

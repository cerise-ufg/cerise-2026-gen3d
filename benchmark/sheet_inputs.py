"""Folha de contato das entradas renderizadas do GSO (linha de cima: entrada az=0; de baixo: referencia az=90)."""
import os
import sys

from PIL import Image, ImageDraw

root = sys.argv[1] if len(sys.argv) > 1 else "/workspace/data/eval"
out = sys.argv[2] if len(sys.argv) > 2 else "/workspace/evidencias/gso_entradas.png"
names = sorted([n for n in os.listdir(root) if os.path.isdir(os.path.join(root, n))])
W, cols = 220, 7
rows = (len(names) + cols - 1) // cols
sheet = Image.new("RGB", (W * cols, rows * (2 * W + 24)), "white")
d = ImageDraw.Draw(sheet)
for i, n in enumerate(names):
    x, y = (i % cols) * W, (i // cols) * (2 * W + 24)
    sheet.paste(Image.open(f"{root}/{n}/input_white.png").resize((W, W)), (x, y))
    sheet.paste(Image.open(f"{root}/{n}/gt_view_az210.png").resize((W, W)), (x, y + W))
    d.text((x + 4, y + 2 * W + 4), n[:34], fill=(0, 0, 0))
os.makedirs(os.path.dirname(out), exist_ok=True)
sheet.save(out)
print(out)

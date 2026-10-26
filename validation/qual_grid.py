"""A4 - grade qualitativa dos resultados do pipeline: entrada | render frontal | 3/4 | close da textura.

python qual_grid.py --root /workspace/results/presets/preset_padrao --objects a,b,c --inputs-dir ... --out x.png
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import render_utils as R  # noqa: E402


def font(sz):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"]:
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def input_image(obj, data, real):
    p = os.path.join(data, obj, "input_white.png")
    if os.path.exists(p):
        return Image.open(p).convert("RGB")
    p = os.path.join(real, obj + ".jpg")
    return Image.open(p).convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--objects", required=True)
    ap.add_argument("--data", default="/workspace/data/eval")
    ap.add_argument("--real", default="/workspace/data/real")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cell", type=int, default=230)
    ap.add_argument("--glb", default="model_grounded.glb")
    a = ap.parse_args()
    objs = a.objects.split(",")
    C = a.cell
    heads = ["Entrada", "Render frontal", "Render 3/4", "Close da textura"]
    head = 40
    img = Image.new("RGB", (C * 4, head + C * len(objs)), "white")
    d = ImageDraw.Draw(img)
    f = font(15)
    for j, h in enumerate(heads):
        d.text((j * C + (C - d.textlength(h, font=f)) / 2, 12), h, fill=(20, 20, 20), font=f)
    for i, o in enumerate(objs):
        y = head + i * C
        im = input_image(o, a.data, a.real)
        im.thumbnail((C, C))
        img.paste(im, ((C - im.width) // 2, y + (C - im.height) // 2))
        glb = os.path.join(a.root, o, a.glb)
        if not os.path.exists(glb):
            d.text((C + 20, y + C // 2), "falhou", fill=(200, 60, 60), font=f)
            continue
        parts = R.load_parts(glb)
        R.normalize_parts(parts, 1.0)
        fr_rgba, _ = R.render(parts, azim=0, elev=10, dist=2.6, fovy=30, res=int(C * 1.5))
        _, fr = R.crop_to_content(fr_rgba, out=C, fill=0.88)
        tq_rgba, _ = R.render(parts, azim=45, elev=20, dist=2.6, fovy=30, res=int(C * 1.5))
        _, tq = R.crop_to_content(tq_rgba, out=C, fill=0.88)
        big, _ = R.render(parts, azim=20, elev=10, dist=2.6, fovy=30, res=1400)
        _, big = R.crop_to_content(big, out=1200, fill=0.95)
        cx, cy, s = 600, 560, 230
        close = big.crop((cx - s, cy - s, cx + s, cy + s)).resize((C, C), Image.LANCZOS)
        img.paste(fr, (C, y))
        img.paste(tq, (2 * C, y))
        img.paste(close, (3 * C, y))
        d.rectangle([3 * C + 1, y + 1, 4 * C - 2, y + C - 2], outline=(200, 200, 200))
        d.text((6, y + C - 18), o.replace("_", " ")[:30], fill=(90, 90, 90), font=font(11))
        d.line([0, y, 4 * C, y], fill=(230, 230, 230))
    img.save(a.out)
    print(a.out)


if __name__ == "__main__":
    main()

"""Grade qualitativa comparando modelos: linhas = objetos; colunas = entrada, GT (vista nova) e, para cada
modelo, render na vista de entrada (az=30) e numa vista nova (az=210), apos alinhamento ao GT.
Usa os renders gravados por evaluate.py."""
import argparse
import os

from PIL import Image, ImageDraw, ImageFont


def font(sz):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"]:
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", required=True)
    ap.add_argument("--labels", default=None)
    ap.add_argument("--objects", default=None)
    ap.add_argument("--data", default="/workspace/data/eval")
    ap.add_argument("--results", default="/workspace/results/bench")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cell", type=int, default=200)
    ap.add_argument("--novel", action="store_true", help="inclui vista nova (az=210) de cada modelo")
    ap.add_argument("--only-novel", action="store_true", help="so a vista nova (az=210): entrada, GT 210 e modelos")
    a = ap.parse_args()
    tags = a.tags.split(",")
    labels = a.labels.split(",") if a.labels else tags
    objs = a.objects.split(",") if a.objects else sorted(
        d for d in os.listdir(a.data) if os.path.isdir(os.path.join(a.data, d)))
    C = a.cell
    cols = [("Entrada (az 30°)", lambda o: os.path.join(a.data, o, "input_white.png"))]
    if a.novel:
        cols.append(("GT (az 210°)", lambda o: os.path.join(a.data, o, "gt_view_az210.png")))
    if a.only_novel:
        cols.append(("GT (az 210°)", lambda o: os.path.join(a.data, o, "gt_view_az210.png")))
    for t, lab in zip(tags, labels):
        if a.only_novel:
            cols.append((lab, lambda o, t=t: os.path.join(a.results, t, o, "render_az210.png")))
            continue
        cols.append((lab, lambda o, t=t: os.path.join(a.results, t, o, "render_az030.png")))
        if a.novel:
            cols.append((lab + " (210°)", lambda o, t=t: os.path.join(a.results, t, o, "render_az210.png")))
    head = 46
    W, H = C * len(cols), head + C * len(objs)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f = font(15)
    for j, (lab, _) in enumerate(cols):
        tw = d.textlength(lab, font=f)
        d.text((j * C + (C - tw) / 2, 14), lab, fill=(20, 20, 20), font=f)
    for i, o in enumerate(objs):
        for j, (_, fn) in enumerate(cols):
            p = fn(o)
            x, y = j * C, head + i * C
            if os.path.exists(p):
                img.paste(Image.open(p).convert("RGB").resize((C, C), Image.LANCZOS), (x, y))
            else:
                d.rectangle([x + 4, y + 4, x + C - 4, y + C - 4], outline=(190, 190, 190), width=1)
                d.text((x + 20, y + C / 2 - 8), "não medido", fill=(140, 140, 140), font=f)
        d.line([0, head + i * C, W, head + i * C], fill=(225, 225, 225))
    img.save(a.out)
    print(a.out)


if __name__ == "__main__":
    main()

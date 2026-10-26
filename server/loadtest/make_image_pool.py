"""Monta o pool de imagens do teste de carga (ordem deterministica, imagens distintas -> sem acerto de cache).

Fontes (ja usadas e licenciadas na frente de modelos): 13 vistas de entrada do Google Scanned Objects (CC-BY 4.0)
em duas versoes (RGBA com alfa e RGB com fundo branco, que passa pela remocao de fundo) e 6 fotos reais CC0.
Cada imagem tambem entra espelhada horizontalmente (outra imagem para o hash do cache) -> 64 imagens.

Uso: python make_image_pool.py <gen3d_root> <saida>
"""
import os
import random
import sys

from PIL import Image, ImageOps


def main(root, out):
    os.makedirs(out, exist_ok=True)
    srcs = []
    ev = os.path.join(root, "data", "eval")
    for name in sorted(os.listdir(ev)):
        d = os.path.join(ev, name)
        if os.path.isdir(d):
            srcs.append((f"gso_{name[:24]}_rgba", os.path.join(d, "input.png")))
            srcs.append((f"gso_{name[:24]}_branco", os.path.join(d, "input_white.png")))
    real = os.path.join(root, "data", "real")
    for f in sorted(os.listdir(real)):
        if f.lower().endswith(".jpg"):
            srcs.append((f"foto_{os.path.splitext(f)[0]}", os.path.join(real, f)))
    items = []
    for tag, p in srcs:
        im = Image.open(p)
        items.append((tag, im, p.lower().endswith(".jpg")))
        items.append((tag + "_esp", ImageOps.mirror(im), p.lower().endswith(".jpg")))
    rnd = random.Random(2026)
    rnd.shuffle(items)
    for i, (tag, im, jpg) in enumerate(items):
        fn = os.path.join(out, f"{i:03d}_{tag}.{'jpg' if jpg else 'png'}")
        if jpg:
            im.convert("RGB").save(fn, quality=92)
        else:
            im.save(fn)
    print(f"{len(items)} imagens em {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

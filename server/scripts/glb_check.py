"""Confere um GLB entregue pelo servidor (sem dependencias alem da biblioteca padrao).

Le o cabecalho glTF 2.0, os chunks JSON/BIN, aplica as transformacoes dos nos para obter a caixa envolvente em
coordenadas do mundo (metros), lista extensoes, materiais e texturas (tipo e resolucao lidos do proprio binario).

    python glb_check.py model.glb [outro.glb ...] [--json saida.json]
"""
from __future__ import annotations

import json
import struct
import sys


def _mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _node_matrix(n):
    if "matrix" in n:
        m = n["matrix"]  # coluna-major
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    t = n.get("translation", [0, 0, 0])
    x, y, z, w = n.get("rotation", [0, 0, 0, 1])
    s = n.get("scale", [1, 1, 1])
    r = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [[r[0][0] * s[0], r[0][1] * s[1], r[0][2] * s[2], t[0]],
            [r[1][0] * s[0], r[1][1] * s[1], r[1][2] * s[2], t[1]],
            [r[2][0] * s[0], r[2][1] * s[1], r[2][2] * s[2], t[2]],
            [0, 0, 0, 1]]


def _img_size(data: bytes):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
        return "png", w, h
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return "jpeg", w, h
            seg = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seg
    return "?", 0, 0


def check(path: str) -> dict:
    b = open(path, "rb").read()
    magic, ver, length = struct.unpack("<4sII", b[:12])
    assert magic == b"glTF" and ver == 2, "nao e glTF 2.0 binario"
    assert length == len(b), "tamanho do cabecalho difere do arquivo"
    clen, ctype = struct.unpack("<II", b[12:20])
    assert ctype == 0x4E4F534A, "primeiro chunk nao e JSON"
    js = json.loads(b[20:20 + clen])
    off = 20 + clen
    blen, btype = struct.unpack("<II", b[off:off + 8])
    assert btype == 0x004E4942, "segundo chunk nao e BIN"
    binc = b[off + 8:off + 8 + blen]
    # caixa envolvente no mundo (cantos da caixa min/max de cada primitiva transformados pelos nos)
    lo, hi = [1e9] * 3, [-1e9] * 3
    tris = 0

    def visit(ni, parent):
        nonlocal tris
        n = js["nodes"][ni]
        m = _mat_mul(parent, _node_matrix(n))
        if "mesh" in n:
            for p in js["meshes"][n["mesh"]]["primitives"]:
                acc = js["accessors"][p["attributes"]["POSITION"]]
                if "indices" in p:
                    tris += js["accessors"][p["indices"]]["count"] // 3
                mn, mx = acc["min"], acc["max"]
                for cx in (mn[0], mx[0]):
                    for cy in (mn[1], mx[1]):
                        for cz in (mn[2], mx[2]):
                            v = [sum(m[r][k] * c for k, c in enumerate((cx, cy, cz, 1))) for r in range(3)]
                            for k in range(3):
                                lo[k], hi[k] = min(lo[k], v[k]), max(hi[k], v[k])
        for c in n.get("children", []):
            visit(c, m)

    ident = [[1 if i == j else 0 for j in range(4)] for i in range(4)]
    scene = js["scenes"][js.get("scene", 0)]
    for ni in scene["nodes"]:
        visit(ni, ident)
    imgs = []
    for im in js.get("images", []):
        bv = js["bufferViews"][im["bufferView"]]
        data = binc[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]]
        kind, w, h = _img_size(data)
        imgs.append(dict(mimeType=im.get("mimeType"), real=kind, w=w, h=h, bytes=bv["byteLength"]))
    mats = js.get("materials", [])
    dims = [round(hi[k] - lo[k], 4) for k in range(3)]
    center = [round((hi[k] + lo[k]) / 2, 4) for k in range(3)]
    return dict(arquivo=path, bytes=len(b), gltf_version=js["asset"].get("version"),
                generator=js["asset"].get("generator"), triangles=tris,
                extensionsUsed=js.get("extensionsUsed", []), extensionsRequired=js.get("extensionsRequired", []),
                materials=len(mats), baseColorTexture=any("baseColorTexture" in m.get("pbrMetallicRoughness", {})
                                                          for m in mats),
                images=imgs, bbox_min_m=[round(x, 4) for x in lo], bbox_max_m=[round(x, 4) for x in hi],
                dims_m=dims, max_dim_m=max(dims), y_min_m=round(lo[1], 4), centro_xz_m=[center[0], center[2]])


def main():
    args = sys.argv[1:]
    out = None
    if "--json" in args:
        i = args.index("--json")
        out = args[i + 1]
        args = args[:i] + args[i + 2:]
    res = []
    for p in args:
        r = check(p)
        bad = {"KHR_draco_mesh_compression", "EXT_meshopt_compression", "KHR_texture_basisu"} & set(
            r["extensionsUsed"])
        r["ok_app"] = (not bad and abs(r["max_dim_m"] - 0.30) < 0.005 and abs(r["y_min_m"]) < 0.002
                       and r["baseColorTexture"])
        res.append(r)
        print(f"{p}: glTF {r['gltf_version']} binario, {r['bytes']} bytes, {r['triangles']} triangulos, "
              f"{r['materials']} material(is), baseColorTexture={r['baseColorTexture']}")
        print(f"   extensoes: {r['extensionsUsed'] or 'nenhuma'} | texturas: "
              + ", ".join(f"{i['real']} {i['w']}x{i['h']} ({i['bytes'] // 1024} KiB)" for i in r["images"]))
        print(f"   caixa no mundo (m): dims={r['dims_m']} maior={r['max_dim_m']} y_min={r['y_min_m']} "
              f"centro_xz={r['centro_xz_m']} -> requisitos do app: {'OK' if r['ok_app'] else 'FALHOU'}")
    if out:
        json.dump(res, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()

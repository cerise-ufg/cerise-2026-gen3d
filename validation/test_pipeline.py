"""A4 - testes funcionais do pipeline imagem->GLB (pytest).

Rodar no container (GPU):  pytest -v validation/test_pipeline.py
Variaveis: GEN3D_TEST_PRESETS (padrao "rapido,padrao,alto"), GEN3D_TEST_IMAGES (lista separada por virgula).
"""
import json
import os
import sys

import numpy as np
import pytest
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.join(HERE, "..", "pipeline")
sys.path.insert(0, PIPE)

import postprocess as PP  # noqa: E402

PRESETS = json.load(open(os.path.join(PIPE, "presets.json")))
TEST_PRESETS = os.environ.get("GEN3D_TEST_PRESETS", ",".join(PRESETS)).split(",")
DEFAULT_IMAGES = [
    "/workspace/data/eval/Schleich_Bald_Eagle/input.png",          # RGBA (GSO)
    "/workspace/data/eval/ACE_Coffee_Mug_Kristen_16_oz_cup/input.png",
    "/workspace/data/real/cc0_teapot.jpg",                          # foto real com fundo (testa remocao de fundo)
]
IMAGES = [p for p in os.environ.get("GEN3D_TEST_IMAGES", ",".join(DEFAULT_IMAGES)).split(",") if os.path.exists(p)]
OUT = os.environ.get("GEN3D_TEST_OUT", "/workspace/results/a4_pytest")


# ----------------------------------------------------------------------------------- testes sem GPU
def _box_glb(path, size=(2.0, 1.0, 0.5), offset=(5.0, 3.0, -2.0)):
    m = trimesh.creation.box(extents=size)
    m.apply_translation(offset)
    m.export(path)


def test_assentar_centralizar_escalar(tmp_path):
    src, dst = str(tmp_path / "box.glb"), str(tmp_path / "box_g.glb")
    _box_glb(src)
    info = PP.ground_center_scale(src, dst, target_size_m=0.30)
    lo, hi = np.array(info["bounds_min"]), np.array(info["bounds_max"])
    assert abs((hi - lo).max() - 0.30) < 1e-6, "maior dimensao deve ser 0,30 m"
    assert abs(lo[1]) < 1e-6, "objeto deve estar apoiado em y=0"
    assert abs((lo[0] + hi[0]) / 2) < 1e-6 and abs((lo[2] + hi[2]) / 2) < 1e-6, "centralizado em x/z"


def test_reducao_textura_sem_extensoes(tmp_path):
    """O caminho usado pelo app (method='none') gera GLB valido e sem extensoes de compressao."""
    src, dst = str(tmp_path / "box.glb"), str(tmp_path / "box_app.glb")
    _box_glb(src)
    PP.compress(src, dst, method="none")
    rep = PP.validate(dst)
    assert rep.get("numErrors", 1) == 0, rep
    assert not set(PP.extensions_used(dst)["extensions"]) & set(PP.FORBIDDEN_EXTENSIONS)


# ----------------------------------------------------------------------------------- testes com GPU
@pytest.fixture(scope="session")
def pipe():
    from gen3d_pipeline import Gen3DPipeline
    return Gen3DPipeline(presets={k: PRESETS[k] for k in TEST_PRESETS}, warmup=False)


_CACHE = {}


def _gen(pipe, img, preset):
    key = (img, preset)
    if key not in _CACHE:
        od = os.path.join(OUT, preset, os.path.splitext(os.path.basename(os.path.dirname(img)) if
                                                         img.endswith("input.png") else os.path.basename(img))[0])
        _CACHE[key] = pipe.generate(img, od, preset=preset)
    return _CACHE[key]


CASES = [(i, p) for p in TEST_PRESETS for i in IMAGES]
IDS = [f"{p}-{os.path.basename(os.path.dirname(i)) if i.endswith('input.png') else os.path.basename(i)}"[:60]
       for i, p in CASES]


@pytest.mark.gpu
@pytest.mark.parametrize("img,preset", CASES, ids=IDS)
def test_glb_valido_khronos(pipe, img, preset):
    out = _gen(pipe, img, preset)
    rep = PP.validate(out["glb_path"])
    assert rep.get("numErrors", 1) == 0, rep


@pytest.mark.gpu
@pytest.mark.parametrize("img,preset", CASES, ids=IDS)
def test_material_com_textura(pipe, img, preset):
    from pygltflib import GLTF2
    out = _gen(pipe, img, preset)
    g = GLTF2().load(out["glb_path"])
    assert len(g.materials) >= 1 and len(g.images) >= 1 and len(g.textures) >= 1
    pbr = g.materials[0].pbrMetallicRoughness
    assert pbr is not None and pbr.baseColorTexture is not None, "material sem baseColorTexture"


@pytest.mark.gpu
@pytest.mark.parametrize("img,preset", CASES, ids=IDS)
def test_sem_draco_meshopt_ktx2(pipe, img, preset):
    """Requisito do app (model-viewer offline + ViroReact): sem Draco/meshopt/KTX2; texturas JPEG/PNG."""
    out = _gen(pipe, img, preset)
    info = PP.extensions_used(out["glb_path"])
    assert not set(info["extensions"]) & set(PP.FORBIDDEN_EXTENSIONS), info
    assert set(info["image_mime"]) <= {"image/jpeg", "image/png"}, info


@pytest.mark.gpu
@pytest.mark.parametrize("img,preset", CASES, ids=IDS)
def test_orcamento_de_faces(pipe, img, preset):
    out = _gen(pipe, img, preset)
    assert 1000 <= out["stats"]["faces"] <= PRESETS[preset]["max_faces"]


@pytest.mark.gpu
@pytest.mark.parametrize("img,preset", CASES, ids=IDS)
def test_bounding_box_metrica(pipe, img, preset):
    out = _gen(pipe, img, preset)
    geo = out["stats"]["geometry"]
    lo, hi = np.array(geo["bounds_min"]), np.array(geo["bounds_max"])
    alvo = PRESETS[preset].get("target_size_m", 0.30)
    assert abs((hi - lo).max() - alvo) < 1e-3
    assert abs(lo[1]) < 1e-4 and abs((lo[0] + hi[0]) / 2) < 1e-4 and abs((lo[2] + hi[2]) / 2) < 1e-4


@pytest.mark.gpu
@pytest.mark.parametrize("img,preset", CASES, ids=IDS)
def test_limite_de_tempo_e_tamanho(pipe, img, preset):
    out = _gen(pipe, img, preset)
    st = out["stats"]
    assert st["total_s"] <= PRESETS[preset]["time_limit_s"], f"{st['total_s']:.1f}s > limite"
    assert st["size_bytes"] <= PRESETS[preset].get("size_limit_bytes", 5_000_000)
    assert out["thumb_path"] and os.path.getsize(out["thumb_path"]) > 1000

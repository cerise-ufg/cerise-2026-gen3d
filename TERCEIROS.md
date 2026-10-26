# Código, pesos, dados e imagens de terceiros (não incluídos neste repositório)

Este repositório contém apenas o que foi produzido no projeto (código, configurações, documentação, resultados
medidos e evidências). Os itens abaixo são de terceiros, sem direito de redistribuição aqui ou grandes demais para o
git; cada um traz a fonte exata, a versão usada nas medições de 26/10/2026 e como obtê-lo de novo. Os caminhos
`~/cerise2026/...` referem-se ao DGX Spark onde os experimentos rodaram.

## 1. Repositórios oficiais dos modelos (`third_party/`, ~1,1 GB)

Clonados por [`scripts/clone.sh`](scripts/clone.sh) com `git clone --depth 1`. Nenhum arquivo rastreado desses
clones foi modificado (`git status` limpo); as adaptações necessárias ficam nos executores de `models/` e no
`docker/Dockerfile` (extensões compiladas para `sm_121`). Para reproduzir exatamente:

```bash
mkdir -p third_party && cd third_party
git clone <url> <pasta> && git -C <pasta> checkout <commit>
```

| pasta | URL | commit usado | data do commit | uso |
|---|---|---|---|---|
| `Hunyuan3D-2` | https://github.com/Tencent-Hunyuan/Hunyuan3D-2.git | `f8db63096c8282cb27354314d896feba5ba6ff8a` | 2025-10-28 | pipeline escolhido (forma + textura); copiado para a imagem Docker |
| `Hunyuan3D-2.1` | https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1.git | `82920d643c0dc2f7bfd7255f45f62d386edfe60c` | 2025-10-17 | benchmark A1 (PBR) |
| `TripoSR` | https://github.com/VAST-AI-Research/TripoSR.git | `107cefdc244c39106fa830359024f6a2f1c78871` | 2026-06-04 | benchmark A1 |
| `InstantMesh` | https://github.com/TencentARC/InstantMesh.git | `08822c52fdc399b93ea00e4fa9e596344ed52ccc` | 2025-01-03 | benchmark A1 |
| `stable-fast-3d` | https://github.com/Stability-AI/stable-fast-3d.git | `ff21fc491b4dc5314bf6734c7c0dabd86b5f5bb2` | 2025-01-22 | clonado; pesos *gated* (não medido) |
| `TRELLIS` | https://github.com/microsoft/TRELLIS.git | `442aa1e1afb9014e80681d3bf604e8d728a86ee7` | 2025-11-05 | bloqueado (sem `spconv`/`cumm` para aarch64) |
| `TRELLIS.2` | https://github.com/microsoft/TRELLIS.2.git | `75fbf0183001ed9876c8dbb35de6b68552ee08bd` | 2026-06-05 | bloqueado (DINOv3 *gated* + extensões CUDA) |
| `nvdiffrast` | https://github.com/NVlabs/nvdiffrast.git | `253ac4fcea7de5f396371124af597e6cc957bfae` | 2025-12-05 | renderizador do benchmark; compilado na imagem |
| `torchmcubes` | https://github.com/tatsy/torchmcubes.git | `a9ac95aa329957ba646e7bb057f825f5dfa77f38` | 2026-10-19 | dependência do TripoSR |

## 2. Pesos do Hugging Face (`~/cerise2026/hf_cache`, ~70 GB)

Baixados por [`models/download_weights.py`](models/download_weights.py) (só os arquivos necessários) para o cache
montado em `/root/.cache/huggingface`. A árvore `hy3dgen_models/` (esperada pelo `hy3dgen`) é feita por
`models/make_local_tree.py` com links simbólicos para os *snapshots* abaixo; `models/fix_turbo_unet.py` converte o
UNet do `hunyuan3d-paint-v2-0(-turbo)` para `.bin` dentro dessa árvore (derivado dos pesos de terceiros, por isso
também não vai no git).

| repositório HF | revisão (`refs/main`) | tamanho no cache | licença (cartão do modelo no HF) | uso |
|---|---|---|---|---|
| `tencent/Hunyuan3D-2` | `9cd649ba6913f7a852e3286bad86bfa9a2d83dcf` | 31 GB | Tencent Hunyuan 3D Community | dit-v2-0(-turbo), vae-v2-0-turbo, delight, paint-v2-0(-turbo) |
| `tencent/Hunyuan3D-2mini` | `f90a0f7df7d5e6f71109cf333f6a95a0ae3194a6` | 4,0 GB | Tencent Hunyuan 3D Community | dit/vae v2-mini-turbo |
| `tencent/Hunyuan3D-2.1` | `0b94677654c57bb9a6b6845cd7b704ccf551d327` | 14 GB | Tencent Hunyuan 3D Community | dit/vae v2-1 e paintpbr-v2-1 |
| `stabilityai/TripoSR` | `5b521936b01fbe1890f6f9baed0254ab6351c04a` | 1,6 GB | MIT | TripoSR |
| `TencentARC/InstantMesh` | `b785b4ecfb6636ef34a08c748f96f6a5686244d0` | 3,1 GB | Apache-2.0 | InstantMesh |
| `sudo-ai/zero123plus-v1.2` | `2da07e89919e1a130c9b5add1584c70c7aa065fd` | 5,2 GB | não declarada no cartão do HF (ver repositório do autor) | multivista do InstantMesh |
| `facebook/dino-vitb16` | `f205d5d8e640a89a2b8ef0369670dfc37cc07fc2` | 328 MB | Apache-2.0 | codificador do InstantMesh |
| `facebook/dinov2-giant` | `611a9d42f2335e0f921f1e313ad3c1b7178d206d` | 4,3 GB | Apache-2.0 | baixado na instalação do Hunyuan3D-2.1 (`logs/install_hy21.log`) |
| `microsoft/TRELLIS-image-large` | `25e0d31ffbebe4b5a97464dd851910efc3002d96` | 3,1 GB | MIT | baixado; modelo bloqueado (ver relatório) |
| `openai/clip-vit-large-patch14` | `32bd64288804d66eefd0ccbe215aa642df71cc41` | 1,6 GB | não declarada no cartão do HF (código do CLIP: MIT, github.com/openai/CLIP) | métrica CLIP do benchmark |

Não baixados: `stabilityai/stable-fast-3d`, `stabilityai/stable-point-aware-3d` e
`facebook/dinov3-vitl16-pretrain-lvd1689m` (condicionamento do TRELLIS.2) são repositórios *gated* (exigem login no
Hugging Face e aceite manual da licença); os pesos `microsoft/TRELLIS.2-4B` também não foram baixados, porque o
modelo ficou bloqueado antes dessa etapa.

## 3. Pesos avulsos

| arquivo | fonte | SHA-256 do arquivo usado | uso |
|---|---|---|---|
| `weights/RealESRGAN_x4plus.pth` (64 MB) | https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth (baixado por `docker/install_hy21.sh`) | `4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1` | super-resolução da textura do Hunyuan3D-2.1 |
| `server/models/u2net/u2net.onnx` (168 MB) | modelo padrão do `rembg==2.0.65`, baixado automaticamente pelo pacote (https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx) e copiado do contêiner de desenvolvimento | `8d10d2f3bb75ae3b6d527c77944fc5e7dcd94b29809d47a739a7a728a912b491` | remoção de fundo no servidor (`server/scripts/start.sh` exige o arquivo) |

## 4. Imagens Docker

Nenhuma imagem é distribuída (cada uma tem ~38 GB e contém a imagem base da NVIDIA). Elas são reconstruídas a partir
deste repositório:

| imagem | ID medido em 26/10/2026 | como construir |
|---|---|---|
| `nvcr.io/nvidia/pytorch:26.05-py3` (base, NVIDIA NGC) | — | `sudo docker pull nvcr.io/nvidia/pytorch:26.05-py3` (licença NVIDIA Deep Learning Container) |
| `cerise26_gen3d:latest` | `sha256:eda57a3575fbfc6d748153dec4bb73ea10ef2ac489ca0581e26c22884c2dd1b9` | `docker/build_image.sh` ou `sudo docker build -f docker/Dockerfile -t cerise26_gen3d:latest .` (precisa de `third_party/Hunyuan3D-2` e `third_party/nvdiffrast` no contexto) |
| `cerise26_gen3d_server:latest` | `sha256:31a17d31f1f1d57ab49c04f72ebb94b650568bad9c60b9b3903444e91c0973e8` | `cd server && sudo docker build -t cerise26_gen3d_server:latest .` (deriva de `cerise26_gen3d:latest`) |

A primeira construção de `cerise26_gen3d:latest` (07:38 UTC, ID `sha256:c5db530e…`) foi substituída pela
reconstrução de 10:17 UTC; os dois registros estão em `logs/anteriores/` e `logs/docker_build.log`.

Ferramentas instaladas dentro das imagens a partir das fontes oficiais: Node.js 22.11.0 (nodejs.org),
`@gltf-transform/cli@4`, `gltfpack`, `gltf-validator`, `@google/model-viewer` e `three` (npm), pacotes Python do PyPI
listados nos Dockerfiles.

## 5. Dados de terceiros que **estão** nos Releases (redistribuição permitida)

* **Google Scanned Objects** (Google Research, via Gazebo Fuel, owner `GoogleResearch`): licença **CC-BY 4.0**.
  13 objetos baixados por `benchmark/gso_download.sh` e renderizados por `benchmark/prepare_gso.py`. Atribuição:
  Downs, L. et al., "Google Scanned Objects: A High-Quality Dataset of 3D Scanned Household Items", ICRA 2022;
  © Google LLC, CC-BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Ver [`data/README.md`](data/README.md).
* **Fotos reais**: Wikimedia Commons / The Metropolitan Museum of Art Open Access, **CC0** (fontes em
  `validation/real/fontes.json`).

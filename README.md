# CERISE 2026 — Geração 3D (imagem → objeto 3D texturizado) para o app de Realidade Aumentada

Frente "Geração 3D — Modelos" do Plano de Trabalho CERISE/EMC/UFG 2026 (Objetivo 1): **A1** análise comparativa de
redes neurais imagem→3D com textura, **A3** otimização do modelo integrado (presets medidos) e **A4** validação
(testes funcionais + análise qualitativa). O app de 2025 (`EduardoCaixeta/cerise-app-ar`) apenas **simulava** o
processamento (`time.sleep(67)` + um `objeto.glb` fixo); aqui fica a rede neural real, medida e empacotada para o
servidor (a etapa seguinte — o servidor HTTP — usa a pasta `server/` deste mesmo repositório).

* Hardware: NVIDIA DGX Spark (GB10 Blackwell, sm_121, **aarch64**, 128 GB de memória unificada), imagem base
  `nvcr.io/nvidia/pytorch:26.05-py3` (PyTorch 2.12, CUDA 13.2), teto de 24 GB de GPU para esta frente.
* Modelo escolhido: **Hunyuan3D-2 Turbo** (forma `hunyuan3d-dit-v2-0-turbo` + FlashVDM, textura
  `hunyuan3d-paint-v2-0-turbo` + delight; o preset "alto" usa o `hunyuan3d-paint-v2-0` completo), com
  pós-processamento rápido e saída GLB pronta para o celular: Y para cima, apoiado em y = 0, maior dimensão 0,30 m,
  textura JPEG reduzida e **sem Draco/meshopt/KTX2** (o `<model-viewer>` offline e o ViroReact do app não têm esses
  decodificadores; Draco/meshopt foram medidos só como comparação).
* Presets medidos no pipeline empacotado (13 objetos GSO + 6 fotos CC0, máquina compartilhada com a produção):
  **rápido** ≈ 24 s / 1,7 MB, **padrão** ≈ 30 s / 2,0 MB, **alto** ≈ 57–82 s / 6,1 MB (medianas; ver relatório).
* Resultados, tabelas e figuras: [`RELATORIO_SECAO.md`](RELATORIO_SECAO.md) e `evidencias/`, `resultados/`.

> **Servidor de geração 3D (Objetivo 2, Atividade 5 e lado servidor da Atividade 2):** pasta [`server/`](server/README.md)
> — API FastAPI assíncrona + fila SQLite + worker de GPU, teste de carga contra a arquitetura de 2025 e teste ponta a
> ponta; relatório em [`RELATORIO_SECAO_SERVIDOR.md`](RELATORIO_SECAO_SERVIDOR.md).
>
> **Correção de 26/10 (textura JPEG):** o `postprocess.compress` chamava `gltf-transform jpeg` sem `--formats`; na
> glTF-Transform 4.5 o padrão é `--formats jpeg`, então a textura PNG gerada pelo Hunyuan3D **não era convertida** e
> os GLBs medidos nesta seção (A3/A4, presets) saíram com textura **PNG** 1024/2048 — os tamanhos de GLB relatados
> aqui correspondem a PNG. A fonte foi corrigida (`--formats "*"`); o servidor já entrega JPEG (preset padrão,
> mesma foto: 2,97 MB → 0,72 MB). A imagem `cerise26_gen3d:latest` ainda contém a versão antiga do arquivo (o
> servidor usa a sua própria rotina); a rodada de presets deve ser repetida para atualizar os tamanhos.

## Resultados principais (medidos no Spark, máquina compartilhada)

| | Tempo/objeto | Aparência | Chamfer ↓ | F@0,05 ↑ | CLIP entrada ↑ |
|---|---|---|---|---|---|
| TripoSR (13 obj.) | 0,9 s | cor por vértice | 0,042 | 0,904 | 0,849 |
| InstantMesh (13 obj.) | 16,5 s | cor por vértice | 0,046 | 0,893 | 0,844 |
| Hunyuan3D-2mini-Turbo (13 obj.) | 65,8 s* | textura UV | 0,035 | 0,930 | 0,893 |
| **Hunyuan3D-2-Turbo** (13 obj.) | 68,8 s* | textura UV | **0,032** | **0,951** | 0,907 |
| Hunyuan3D-2.0 padrão (4 obj.) | 229,5 s | textura UV | 0,039 | 0,918 | 0,933 |
| Hunyuan3D-2.1 PBR (2 obj.) | 242,9 s | textura PBR | 0,032 | 0,949 | 0,883 |

\* antes das otimizações e sob carga de CPU ≈ 40. Depois do A3 (pós-processamento rápido, octree, faces, textura),
o pipeline empacotado mede **rápido 23,9 s / 1,65 MB**, **padrão 30,4 s / 2,01 MB** e **alto 82,1 s / 6,14 MB**
(medianas no GSO, com a produção ativa), pico de 14,5 GB. A4: **58/58 testes pytest aprovados**; GLBs carregam no
`<model-viewer>` e no three.js. Bloqueios documentados: TRELLIS (sem `spconv` para aarch64) e TRELLIS.2/SF3D/SPAR3D
(repositórios HF *gated*, pendente login/aceite do Eduardo). Para a etapa do servidor: `~/cerise2026/gen3d/READY.json`
(cópia em `resultados/READY.json`).

## Estrutura

| pasta | conteúdo |
|---|---|
| `models/` | executores instrumentados por etapa: `hy2.py` (família Hunyuan3D-2: 2.0, turbo, 2mini, 2.1-forma), `hy21.py` (Hunyuan3D-2.1 com PBR, adaptado para aarch64), `triposr_runner.py`, `instantmesh_runner.py`; `download_weights.py` (baixa só os arquivos necessários) e `make_local_tree.py`/`fix_turbo_unet.py` (árvore `HY3DGEN_MODELS`) |
| `benchmark/` | preparo do conjunto GSO (`gso_download.sh`, `prepare_gso.py`), renderizador nvdiffrast (`render.py`), métricas (`metrics.py`: normalização + ICP com escala, Chamfer, F-score, CLIP), execução (`run_model.py`, filas `queue_*.sh`), avaliação (`evaluate.py`), agregação/gráficos (`aggregate.py`, `aggregate_a3.py`, `grid_compare.py`), presets (`run_presets.py`) |
| `pipeline/` | **pipeline empacotado**: `gen3d_pipeline.py` (`Gen3DPipeline`, carga quente única), `presets.json` (rápido/padrão/alto), `postprocess.py` (assentar/centralizar/escala 0,30 m, redução de textura JPEG com glTF-Transform — Draco/meshopt só para comparação —, validação Khronos, miniatura), `render_utils.py`, `write_ready.py` (gera o `READY.json` para a etapa do servidor) |
| `validation/` | A4: `test_pipeline.py` (pytest), `qual_grid.py` (grade qualitativa), `viewer_check.py` + `viewer/index.html` (carregamento no `<model-viewer>` e three.js via Playwright), fotos CC0 (`find_cc0_photos.py`, `download_cc0.py`, `real/fontes.json`) |
| `docker/` | `Dockerfile` da imagem `cerise26_gen3d:latest` e scripts de instalação usados no container de desenvolvimento |
| `evidencias/` | figuras do relatório (gráficos, grades, prints de terminal e do visualizador) |
| `resultados/` | tabelas `.csv/.md` e `.json` com todas as métricas medidas |

Não versionados (ficam no Spark): pesos (`~/cerise2026/hf_cache`, ~70 GB), `~/cerise2026/gen3d/hy3dgen_models`
(árvore de links + UNet convertido), fontes oficiais dos modelos (`third_party/`, clonados por `scripts/clone.sh`),
dados GSO (`data/`) e GLBs gerados (`results/`).

## Como rodar (no Spark)

```bash
# 1) imagem
cd ~/cerise2026/gen3d && sudo docker build -f docker/Dockerfile -t cerise26_gen3d:latest .
# 2) pesos (uma vez; cache HF compartilhado entre frentes)
sudo docker run --rm --gpus all --ipc=host -v ~/cerise2026/hf_cache:/root/.cache/huggingface \
  -v ~/cerise2026/gen3d/hy3dgen_models:/opt/gen3d/hy3dgen_models cerise26_gen3d:latest \
  bash -c "cd models && python download_weights.py hy2 clip && python make_local_tree.py && python fix_turbo_unet.py"
# 3) gerar um objeto
sudo docker run --rm --gpus all --ipc=host -v ~/cerise2026/hf_cache:/root/.cache/huggingface \
  -v ~/cerise2026/gen3d/hy3dgen_models:/opt/gen3d/hy3dgen_models -v /tmp/saida:/saida cerise26_gen3d:latest \
  python -c "import sys; sys.path.insert(0,'pipeline'); from gen3d_pipeline import Gen3DPipeline; \
p=Gen3DPipeline(); print(p.generate('pipeline/assets/warmup.png','/saida','padrao')['stats'])"
```

```python
from gen3d_pipeline import Gen3DPipeline
pipe = Gen3DPipeline()                         # carrega forma + textura uma vez (≈ 12 GB) e aquece
out = pipe.generate("foto.jpg", "/tmp/obj1", preset="padrao")   # "rapido" | "padrao" | "alto"
out["glb_path"], out["thumb_path"], out["stats"]["times"], out["stats"]["size_bytes"]
```

Testes (A4): `pytest -v validation/test_pipeline.py` (dentro do container, com GPU).
Benchmark (A1/A3): `benchmark/run_model.py --config <cfg>` → `benchmark/evaluate.py --tags <cfg>` →
`benchmark/aggregate.py`.

## Licenças e dados

* Código desta pasta: uso acadêmico no projeto CERISE/UFG.
* Hunyuan3D-2 / 2.1: *Tencent Hunyuan 3D Community License* (não se aplica na UE, Reino Unido e Coreia do Sul; ver
  limites de uso comercial na licença). TripoSR: MIT. InstantMesh: Apache-2.0.
* Google Scanned Objects (GoogleResearch, Gazebo Fuel): **CC-BY 4.0** — © Google LLC.
* Fotos reais: Wikimedia Commons / The Met Open Access, **CC0** (fontes em `validation/real/fontes.json`).

# CERISE 2026 — Geração 3D (imagem → objeto 3D texturizado) e servidor de geração 3D

Repositório da frente **Realidade Aumentada — Geração 3D** do Plano de Trabalho 2026 "Pesquisa, Desenvolvimento e
Inovação em Gêmeos Digitais, Tecnologias Imersivas, Robótica e Navegação Autônoma no escopo do CERISE/EMC/UFG".

* **Autor:** Eduardo Martins de Carvalho Caixeta (bolsista, CERISE/EMC/UFG)
* **Coordenação da frente:** Prof. Dr. Carlos Galvão Pinheiro Junior (Realidade Aumentada)
* **Execução e medições:** 26/10/2026, no NVIDIA DGX Spark (GB10 Blackwell, `sm_121`, **aarch64**, 128 GB de
  memória unificada), imagem base `nvcr.io/nvidia/pytorch:26.05-py3` (PyTorch 2.12, CUDA 13.2), com teto de 24 GB
  de GPU para esta frente e a produção de IA do Spark ativa na mesma máquina.

## Atividades do plano cobertas

| objetivo / atividade | o que foi feito | onde |
|---|---|---|
| **O1 · A1** — análise comparativa de redes imagem→3D com textura | tabela da literatura (10 modelos) e *benchmark* prático de 6 modelos/variantes em 13 objetos do Google Scanned Objects (Chamfer, F-score, CLIP, tempo por etapa, pico de GPU) | `RELATORIO_SECAO.md` §3, `benchmark/`, `models/`, `resultados/a1_*` |
| **O1 · A3** — otimização do modelo integrado e presets | 10 variantes do Hunyuan3D-2 Turbo (série sequencial e série intercalada), compressão do GLB e presets rápido/padrão/alto medidos no pipeline empacotado | `RELATORIO_SECAO.md` §4, `pipeline/`, `resultados/a3*`, `resultados/presets_*` |
| **O1 · A4** — validação funcional e qualitativa | 58 testes pytest, carregamento no `<model-viewer>`/three.js, grades qualitativas com GSO e fotos reais CC0, casos de falha | `RELATORIO_SECAO.md` §5, `validation/`, `resultados/a4_pytest/` |
| **O1 · A2 (lado servidor)** — integração do modelo ao app | motor do servidor sobre o `Gen3DPipeline`, GLB no formato do app e endpoint legado do app de 2025 | `server/`, `RELATORIO_SECAO_SERVIDOR.md` §6 |
| **O2 · A5** — arquitetura do servidor, gargalos com múltiplas requisições, otimização, escalabilidade e confiabilidade | reprodução medida do servidor de 2025, nova arquitetura (API assíncrona + fila SQLite + worker de GPU), suíte de carga, teste ponta a ponta | `server/`, `RELATORIO_SECAO_SERVIDOR.md` |

O app de RA de 2025 (`EduardoCaixeta/cerise-app-ar`) apenas **simulava** a geração no servidor (`time.sleep(67)` e
um `objeto.glb` fixo); aqui ficam a rede neural real, escolhida, medida e empacotada (`pipeline/`), e o servidor que
a atende com fila e worker de GPU (`server/`).

Os dois relatórios técnicos da frente estão na raiz: [`RELATORIO_SECAO.md`](RELATORIO_SECAO.md) (modelos, A1/A3/A4)
e [`RELATORIO_SECAO_SERVIDOR.md`](RELATORIO_SECAO_SERVIDOR.md) (servidor, O2-A5 e A2).

## Resultados principais (medidos no Spark, máquina compartilhada)

**A1 — comparação de modelos** (`resultados/a1_tabela.csv`; tempos antes das otimizações e sob carga de CPU):

| modelo | objetos | tempo mediano | aparência | Chamfer ↓ | F@0,05 ↑ | F@0,1 ↑ | CLIP entrada ↑ | CLIP vistas novas ↑ | pico GPU |
|---|---|---|---|---|---|---|---|---|---|
| TripoSR | 13/13 | 0,9 s | cor por vértice | 0,042 | 0,904 | 0,977 | 0,849 | 0,809 | 4,2 GB |
| InstantMesh | 13/13 | 16,5 s | cor por vértice | 0,046 | 0,893 | 0,963 | 0,844 | 0,836 | 23,2 GB |
| Hunyuan3D-2mini-Turbo | 13/13 | 65,8 s | textura UV | 0,035 | 0,930 | 0,985 | 0,893 | 0,859 | 13,6 GB |
| **Hunyuan3D-2-Turbo** (escolhido) | 13/13 | 68,8 s | textura UV | **0,032** | **0,951** | **0,992** | 0,907 | 0,854 | 14,6 GB |
| Hunyuan3D-2.0 padrão | 4/4 | 229,5 s | textura UV | 0,039 | 0,918 | 0,980 | 0,933 | 0,884 | 14,5 GB |
| Hunyuan3D-2.1 PBR | 2/2 | 242,9 s | textura PBR | 0,032 | 0,949 | 0,994 | 0,883 | 0,878 | 13,8 GB |

Autoteste das métricas (malha de referência transformada): Chamfer médio 0,0042 e F@0,05 ≥ 0,976. TRELLIS, TRELLIS.2,
Stable Fast 3D e SPAR3D ficaram bloqueados (sem `spconv`/`cumm` para aarch64; repositórios *gated*, pendentes de login no Hugging Face e aceite das licenças pelo Eduardo), com a evidência
em `resultados/trellis_bloqueio_pypi.txt` e no relatório.

**A3 — otimização** (série intercalada, 4 objetos, `resultados/a3i_tabela.csv`): tempo mediano base 63,9 s →
pós-processamento rápido 37,5 s → octree 256 41,0 s, sem perda de geometria (F@0,05 0,949–0,951). Sem FlashVDM a
etapa de forma passa de 3,5 s para 115,7 s (`resultados/a3_tabela.csv`); o *paint* completo eleva o CLIP de vistas
novas de 0,846 para 0,893 e foi usado só no preset alto.

**Presets do pipeline empacotado** (13 GSO + 6 fotos CC0, `resultados/READY.json` e `resultados/presets_tabela.csv`):
rápido **23,9 s / 1,65 MB**, padrão **30,4 s / 2,01 MB**, alto **82,1 s / 6,14 MB** (medianas no GSO), pico de
14,5 GB; carga a frio 115 s + aquecimento 79 s; 11,4 GB após a carga.

**A4 — validação:** 58/58 testes pytest aprovados (38 + 20; `resultados/a4_pytest/`), 7/7 GLBs carregados no
`<model-viewer>` e no three.js (`resultados/viewer/viewer_report.json`).

**Servidor (O2-A5)** — `server/resultados/tabelas/`:

| configuração (33 jobs) | sucesso | taxa de erro | latência p50 / p95 / p99 | vazão com 16 clientes |
|---|---|---|---|---|
| 2025: Flask síncrono, sem trava | 3/33 | 90,9 % | 12,3 / 12,5 / 12,5 s | 0 jobs/min |
| 2025: Flask síncrono, com trava | 33/33 | 0 % | 52,1 / 199,0 / 215,7 s | 4,37 jobs/min |
| 2026: fila + 1 worker | 33/33 | 0 % | 49,6 / 174,1 / 188,8 s | 4,99 jobs/min |
| 2026: fila + 2 slots | 33/33 | 0 % | 46,5 / 155,6 / 167,8 s | 5,63 jobs/min |

Com 16 clientes simultâneos o p95 caiu de 210,2 s (2025 com trava) para 184,1 s (1 worker) e 164,4 s (2 slots). Com
a GPU ocupada, a API nova respondeu com p95 de 6,6–6,7 ms e p99 ≤ 9,2 ms (Flask de 2025: p95 123,4 ms, p99 228,6 ms).
Acerto de cache em 0,02 s; 8 pedidos idênticos simultâneos geraram 1 execução de GPU (12,31 s); *backpressure* com
fila máxima 8: 9 aceitos e 7 recusados com HTTP 429 em 0,32 s. Teste ponta a ponta a partir do Windows (preset
padrão): GLB pronto em 16,1 s, 0,72 MB, baixado em 0,33 s, validado com 0 erros no Khronos glTF-Validator.

> **Correção de 26/10 (textura JPEG):** o `postprocess.compress` chamava `gltf-transform jpeg` sem `--formats`; na
> glTF-Transform 4.5 o padrão é `--formats jpeg`, então a textura PNG gerada pelo Hunyuan3D **não era convertida** e
> os GLBs medidos em A3/A4 e nos presets saíram com textura **PNG** — os tamanhos de GLB acima correspondem a PNG. A
> fonte foi corrigida (`--formats "*"`; a versão anterior está preservada em `pipeline/postprocess.py.bak_20261026`);
> o servidor já entrega JPEG (preset padrão, mesma foto: 2,97 MB → 0,72 MB). A imagem `cerise26_gen3d:latest` ainda
> contém a versão antiga do arquivo, e a rodada de presets deve ser repetida para atualizar os tamanhos.

## Estrutura do repositório

| pasta / arquivo | conteúdo |
|---|---|
| `models/` | executores instrumentados por etapa: `hy2.py` (família Hunyuan3D-2: 2.0, turbo, 2mini, forma do 2.1), `hy21.py` (Hunyuan3D-2.1 PBR adaptado para aarch64), `triposr_runner.py`, `instantmesh_runner.py`; `download_weights.py`, `make_local_tree.py`, `fix_turbo_unet.py` (árvore `HY3DGEN_MODELS`) |
| `benchmark/` | conjunto GSO (`gso_list.sh`, `gso_download.sh`, `prepare_gso.py`), renderizador nvdiffrast (`render.py`), métricas (`metrics.py`, `selftest_metrics.py`), execução (`run_model.py`, filas `queue_*.sh`, `launch_*.sh`, `chain_guarded.sh`), avaliação (`evaluate.py`, `eval_*.sh`), agregação e gráficos (`aggregate*.py`, `grid_compare.py`, `compression_table.py`), presets (`run_presets.py`) |
| `pipeline/` | pipeline empacotado: `gen3d_pipeline.py` (`Gen3DPipeline`), `presets.json`, `postprocess.py` (assentar/centralizar/escala 0,30 m, textura JPEG, validação, miniatura), `render_utils.py`, `write_ready.py`, `assets/warmup.png`; `postprocess.py.bak_20261026` (versão anterior à correção da textura) |
| `validation/` | A4: `test_pipeline.py` (pytest), `qual_grid.py`, `viewer_check.py` + `viewer/index.html`, busca e download das fotos CC0, `real/` (6 fotos CC0 + `fontes.json`) |
| `docker/` | `Dockerfile` da imagem `cerise26_gen3d:latest`, `build_image.sh`, `smoke_image.sh` e scripts de instalação por etapa |
| `server/` | servidor de geração 3D: `cerise_gen3d_server/` (API FastAPI, fila SQLite, worker, motor, métricas, gerência), `baseline_2025/`, `loadtest/`, `tests/`, `scripts/`, `docs/` (diagramas), `compose.yaml`, `gen3d.env`, `Dockerfile`, `resultados/` (carga, tabelas, ponta a ponta, pytest, registros de jobs) — ver [`server/README.md`](server/README.md) |
| `scripts/` | utilitários (clonagem dos repositórios oficiais, consultas ao HF, estatísticas, montagens de figuras, sincronização com o Spark, `empacotar_releases.sh`); `gso_download_inicial.sh` é a primeira versão do download do GSO, antes da troca de dois objetos |
| `resultados/` | tabelas consolidadas (`a1_*`, `a1_parcial_*`, `a3_*`, `a3i_*`, `presets_*`, `a3_compressao.json`), `READY.json`, saída do pytest, `logs_execucao/` (seleção de logs citada no relatório), registros da imagem Docker |
| `results/` | métricas brutas de **todas** as rodadas (`summary.json`, `metrics.csv`, `stats.json` por objeto) nas pastas `bench/`, `a3/`, `a3i/`, `presets/`, `a4_pytest/`, `test/`; os GLBs e renderizações correspondentes estão nos Releases |
| `logs/` | logs completos das execuções no Spark (instalação, *build* da imagem, filas A1/A3, avaliações, presets, A4); `logs/anteriores/` guarda o registro da primeira construção da imagem |
| `data/` | índices e metadados do conjunto de avaliação (`gso_names.txt`, `eval/index.json`, `eval/*/info.json`) e a atribuição dos dados — ver [`data/README.md`](data/README.md) |
| `evidencias/` | figuras dos relatórios (gráficos matplotlib, grades qualitativas, capturas do visualizador e do Swagger, prints de terminal) |
| [`RELEASES.md`](RELEASES.md) | arquivos grandes publicados nos Releases (GLBs, renderizações, dados GSO, banco e jobs do servidor), com SHA-256 e instruções de extração |
| [`TERCEIROS.md`](TERCEIROS.md) | código, pesos e imagens de terceiros não incluídos, com URL, commit/revisão e como obter |

## Como reproduzir

Pré-requisitos: máquina NVIDIA com Docker + `nvidia-container-toolkit` (os comandos abaixo foram usados no DGX
Spark, aarch64), os repositórios oficiais em `third_party/` nos commits de [`TERCEIROS.md`](TERCEIROS.md) e os pesos
no cache do Hugging Face.

```bash
# 0) repositórios oficiais dos modelos (commits exatos em TERCEIROS.md)
bash scripts/clone.sh
# 1) imagem do pipeline
sudo docker build -f docker/Dockerfile -t cerise26_gen3d:latest .
# 2) pesos (uma vez; cache HF montado em /root/.cache/huggingface)
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

* **Dados de avaliação:** `bash benchmark/gso_download.sh` e `python benchmark/prepare_gso.py`, ou extrair
  `gen3d_dados_gso_cc0.tar.gz` dos Releases na raiz do repositório.
* **Benchmark (A1/A3):** `benchmark/run_model.py --config <cfg>` → `benchmark/evaluate.py --tags <cfg>` →
  `benchmark/aggregate.py` (filas usadas em `benchmark/queue_*.sh` e `benchmark/chain_guarded.sh`).
* **Testes (A4):** `pytest -v validation/test_pipeline.py` dentro do contêiner, com GPU (`validation/run_a4.sh`).
* **Servidor:** `cd server && sudo docker build -t cerise26_gen3d_server:latest . && bash scripts/start.sh`
  (exige `models/u2net/u2net.onnx`, ver `TERCEIROS.md`); testes sem GPU com `bash scripts/run_pytest.sh`; suíte de
  carga em `server/loadtest/`. Detalhes, contrato da API e operação em [`server/README.md`](server/README.md).

O GLB entregue ao app é Y-para-cima, apoiado em y = 0, centralizado em x/z, com maior dimensão de 0,30 m, textura
JPEG reduzida e **sem Draco/meshopt/KTX2** (o `<model-viewer>` offline e o ViroReact do app não têm esses
decodificadores; Draco e meshopt foram medidos só como comparação). O servidor apaga a foto logo após o
processamento e os modelos gerados em até 7 dias (`GEN3D_RETENTION_DAYS=7`).

## Artefatos grandes (Releases)

GLBs de todas as rodadas (benchmark A1, variantes A3/A3i, presets, pytest e testes), renderizações usadas nas
métricas, os 13 objetos GSO com as renderizações de avaliação, as fotos CC0, o banco SQLite e os jobs de teste do
servidor, o *pool* de imagens da suíte de carga e as saídas do teste ponta a ponta estão em arquivos `.tar.gz`
publicados nos Releases. A lista com tamanho, SHA-256, conteúdo e o comando de extração está em
[`RELEASES.md`](RELEASES.md); extraídos na raiz do repositório, os pacotes recriam as pastas `results/`, `data/` e
`server/{results,data,loadtest/pool,e2e_out*}` exatamente como estavam no Spark e no Windows.

## O que não está aqui e por quê

* **Código e pesos de terceiros** (sem direito de redistribuição neste repositório ou grandes demais): clones
  oficiais em `third_party/` (~1,1 GB), pesos do Hugging Face (~70 GB em `~/cerise2026/hf_cache`), árvore
  `hy3dgen_models/` com o UNet convertido, `RealESRGAN_x4plus.pth` e `u2net.onnx`. Fonte, commit/revisão e SHA-256
  em [`TERCEIROS.md`](TERCEIROS.md).
* **Imagens Docker** `cerise26_gen3d:latest` e `cerise26_gen3d_server:latest` (~38 GB cada, contêm a imagem base da
  NVIDIA): reconstruídas pelos Dockerfiles deste repositório; IDs medidos em `TERCEIROS.md`.
* **Segredos:** nenhum segredo foi criado nesta frente. O servidor aceita chaves de API (`GEN3D_API_KEYS`) num arquivo
  `server/gen3d.secrets.env`, que nunca deve ser versionado (está no `.gitignore`); esse arquivo não existe hoje,
  porque o servidor não foi exposto publicamente.
* **Artefatos regeneráveis:** `__pycache__/`, `.pytest_cache/`, diretórios `build/` das extensões compiladas.
* **Cópias intermediárias** de sincronização (pasta local `_spark/` e versões antigas de README/relatório no Spark):
  substituídas pelos arquivos atuais e pelo histórico do git.

## Licença

Nenhum arquivo `LICENSE` foi adicionado, por decisão do autor. O código é de uso acadêmico no projeto CERISE/EMC/UFG;
sem licença explícita, valem os direitos autorais padrão do autor. Componentes de terceiros seguem as próprias
licenças: Hunyuan3D-2/2.1 sob a *Tencent Hunyuan 3D Community License* (não se aplica na UE, no Reino Unido e na
Coreia do Sul; ver limites de uso comercial), TripoSR (MIT), InstantMesh (Apache-2.0); Google Scanned Objects sob
**CC-BY 4.0** (© Google LLC); fotos reais **CC0** (Wikimedia Commons / The Met Open Access).

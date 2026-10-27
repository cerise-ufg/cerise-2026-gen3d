# Geração 3D a partir de fotografia e servidor de geração

Roteiro de implementação do repositório `cerise-2026-gen3d` (CERISE/EMC/UFG, Plano de Trabalho 2026), por Eduardo Martins de Carvalho Caixeta. Os resultados de referência e a metodologia completa estão em [`RELATORIO_SECAO.md`](RELATORIO_SECAO.md) e [`RELATORIO_SECAO_SERVIDOR.md`](RELATORIO_SECAO_SERVIDOR.md).

## O que será reproduzido

Este roteiro mostra como montar, a partir do repositório `cerise-2026-gen3d`, o pipeline que transforma a fotografia de um objeto em um modelo 3D texturizado (GLB) para o celular e o servidor que atende vários usuários com fila e um worker de GPU. O modelo é o Hunyuan3D-2 Turbo com FlashVDM, com três *presets* (rápido, padrão e alto). Os caminhos citados são relativos à raiz do repositório.

Ao final, você terá:

- a imagem Docker `cerise26_gen3d:latest` e a classe `Gen3DPipeline`, que gera um GLB com maior dimensão de 0,30 m, apoiado em y = 0, com textura JPEG e sem Draco, meshopt ou KTX2 (Objetivo 1, Atividade 3);
- as métricas do benchmark A1 (Chamfer, F-score, CLIP, tempo por etapa e pico de GPU) recalculadas em 13 objetos do Google Scanned Objects (Objetivo 1, Atividade 1);
- a validação A4: 58 testes pytest e o carregamento no `<model-viewer>` e no three.js (Objetivo 1, Atividade 4);
- o servidor de geração 3D (API FastAPI, fila SQLite e worker de GPU em Docker Compose), testado com curl, com o endpoint legado de 2025, com o aplicativo e com a suíte de carga (Objetivo 2, Atividade 5, e lado servidor da Atividade 2 do Objetivo 1).

## Requisitos

**Tabela: Requisitos para reproduzir a geração 3D e o servidor**

| Item | Usado no projeto | Para reproduzir |
|---|---|---|
| GPU | NVIDIA DGX Spark: GB10 Blackwell (sm_121), 128 GB de memória unificada, teto de 24 GB para esta frente | GPU NVIDIA com mais de 24 GB; picos medidos de 14,5 GB (pipeline) e, no worker, 18,9 GB alocados (22,9 GB no `nvidia-smi`); com 24 GB, suba o worker sem o *preset* alto (ver Problemas comuns) |
| Sistema | Ubuntu 24.04, CPU aarch64 | Linux; x86_64 com as adaptações indicadas (não testado) |
| Contêineres | Docker com Compose v2 e NVIDIA Container Toolkit; base `nvcr.io/nvidia/pytorch:26.05-py3` (PyTorch 2.12, CUDA 13.2, Python 3.12) | as mesmas versões e driver compatível com CUDA 13 |
| Disco | pesos ~70 GB (só o pipeline: ~37 GB), imagem ~38 GB, Releases ~1,9 GB | 150 GB livres |
| Cliente | notebook Windows com Python 3 e `requests`; Android SDK com emulador | qualquer máquina com `curl` e `ssh` |
| Contas | GitHub com acesso à organização `cerise-ufg` e GitHub CLI (`gh`) | as mesmas; conta no Hugging Face é opcional |

Tempo estimado: 12 min para construir a imagem; o download dos pesos depende da rede; 3 min para carregar e aquecer o modelo; cerca de 20 min para o Hunyuan3D-2 Turbo no benchmark; 6 min para os testes A4; 40 min para a suíte de carga. Os repositórios da organização são privados: solicite acesso ao bolsista. Os pesos do Hunyuan3D-2 seguem a *Tencent Hunyuan 3D Community License*, que não vale na União Europeia, no Reino Unido e na Coreia do Sul.

## Obtenção do código e dos dados

1. Autentique a GitHub CLI (escolha HTTPS e aceite autenticar o Git com as suas credenciais do GitHub) e clone o repositório exatamente em `~/cerise2026/gen3d`, caminho usado por vários scripts.

```bash
gh auth login
gh repo clone cerise-ufg/cerise-2026-gen3d ~/cerise2026/gen3d
mkdir -p ~/cerise2026/hf_cache
```

2. Clone o Hunyuan3D-2 e o nvdiffrast nos commits usados, necessários para a imagem. Os demais modelos do benchmark e seus commits estão em [`TERCEIROS.md`](TERCEIROS.md).

```bash
mkdir -p ~/cerise2026/gen3d/third_party && cd ~/cerise2026/gen3d/third_party
git clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2.git Hunyuan3D-2
git -C Hunyuan3D-2 checkout f8db63096c8282cb27354314d896feba5ba6ff8a
git clone https://github.com/NVlabs/nvdiffrast.git nvdiffrast
git -C nvdiffrast checkout 253ac4fcea7de5f396371124af597e6cc957bfae
```

3. Baixe os pacotes do Release `dados-2026-10-26` (ou pela página Releases), confira o SHA-256 e extraia-os na raiz do repositório. O pacote `gen3d_dados_gso_cc0.tar.gz` traz o conjunto de avaliação, necessário ao benchmark e aos testes; `gen3d_servidor_brutos.tar.gz` traz as imagens da suíte de carga; os demais servem de referência (lista em [`RELEASES.md`](RELEASES.md)).

```bash
cd ~/cerise2026/gen3d
gh release download dados-2026-10-26 -R cerise-ufg/cerise-2026-gen3d -D ~/gen3d_releases
(cd ~/gen3d_releases && sha256sum -c SHA256SUMS)
for f in ~/gen3d_releases/gen3d_*.tar.gz; do tar -xzf "$f"; done
```

Sem o Release, `bash benchmark/gso_download.sh` baixa os objetos (CC-BY 4.0), `benchmark/prepare_gso.py`, no contêiner de desenvolvimento, renderiza `data/eval/`, e as fotos CC0 de `validation/real/` devem ser copiadas para `data/real/`.

## Imagem do pipeline e pesos

1. Construa a imagem, que compila as extensões CUDA para `TORCH_CUDA_ARCH_LIST=12.1`, e confira-a.

```bash
cd ~/cerise2026/gen3d
sudo docker build -f docker/Dockerfile -t cerise26_gen3d:latest .
bash docker/smoke_image.sh
```

A conferência deve mostrar `cuda True`, `gen3d_pipeline ok; presets: ['rapido', 'padrao', 'alto']`, Node `v22.11.0` e glTF-Transform `4.5.1` (`resultados/docker_smoke.txt`).

2. Em x86_64 (não testado), antes do build, troque o Node para x64 e a arquitetura CUDA pela da sua GPU (8.9 no exemplo), também nos scripts `docker/install_*.sh`, que redefinem `TORCH_CUDA_ARCH_LIST` ao compilar as extensões de TripoSR, InstantMesh e Hunyuan3D-2.1 no benchmark, e confira se a imagem base tem variante amd64 no catálogo NGC.

```bash
sed -i -e 's/linux-arm64/linux-x64/g' \
  -e 's/ARCH_LIST="12.1"/ARCH_LIST="8.9"/' docker/Dockerfile
sed -i 's/ARCH_LIST="12.1"/ARCH_LIST="8.9"/' docker/install_*.sh
```

3. Baixe os pesos e monte a árvore `hy3dgen_models/`. O conjunto `hy2` traz forma, textura e *delight* do Hunyuan3D-2 e o 2mini; `clip` traz o CLIP das métricas. `make_local_tree.py` converte o UNet do módulo de textura para `.bin`, único formato aceito pelo carregador oficial, e `fix_turbo_unet.py` baixa o `.bin` do módulo turbo, cujo `.safetensors` tem chaves incompatíveis.

```bash
sudo docker run --rm --gpus all --ipc=host \
  -v ~/cerise2026/hf_cache:/root/.cache/huggingface \
  -v ~/cerise2026/gen3d/hy3dgen_models:/opt/gen3d/hy3dgen_models \
  cerise26_gen3d:latest bash -c "cd models \
  && python download_weights.py hy2 clip --hy3dgen-dir /opt/gen3d/hy3dgen_models \
  && python make_local_tree.py && python fix_turbo_unet.py"
```

Para o benchmark completo, acrescente `hy21 triposr instantmesh`. A árvore usa links absolutos: monte o cache sempre em `/root/.cache/huggingface`.

## Geração de um objeto

1. Gere um GLB a partir de uma foto. O exemplo carrega os *presets* rápido e padrão: o `Gen3DPipeline` carrega forma e textura (~11,4 GB, cerca de 115 s) e aquece os dois *presets* (cerca de 80 s) uma vez, valores medidos com esses dois *presets* (`resultados/READY.json`); depois, cada geração leva dezenas de segundos.

```bash
mkdir -p /tmp/saida
sudo docker run --rm --gpus all --ipc=host \
  -v ~/cerise2026/hf_cache:/root/.cache/huggingface \
  -v ~/cerise2026/gen3d/hy3dgen_models:/opt/gen3d/hy3dgen_models \
  -v ~/cerise2026/gen3d/validation/real:/fotos:ro -v /tmp/saida:/saida \
  cerise26_gen3d:latest python -c "import sys; sys.path.insert(0,'pipeline'); \
from gen3d_pipeline import Gen3DPipeline, DEFAULT_PRESETS; \
p=Gen3DPipeline(presets={k: DEFAULT_PRESETS[k] for k in ['rapido','padrao']}); \
print(p.generate('/fotos/cc0_rooster.jpg','/saida','padrao')['stats'])"
```

2. Confira em `/tmp/saida` o `model.glb` (entregue ao app), os intermediários, `thumb.png` e `stats.json` (tempo por etapa, faces, tamanho, dimensões e pico de GPU). Sem o argumento `presets`, o `Gen3DPipeline()` carrega também o alto, que usa o módulo de textura completo; medido sozinho, o alto levou 107 s de carga e 118 s de aquecimento (`resultados/READY.json`).

**Tabela: Presets de pipeline/presets.json (forma com 5 passos e FlashVDM) e tempo mediano no GSO (resultados/READY.json)**

| Preset | Octree | Faces | Textura gerada / entregue | Módulo de textura | Tempo mediano |
|---|---|---|---|---|---|
| rapido | 256 | 10 mil | 1024 / 1024 px | paint-v2-0-turbo | 23,9 s |
| padrao | 384 | 20 mil | 2048 / 1024 px | paint-v2-0-turbo | 30,4 s |
| alto | 384 | 40 mil | 2048 / 2048 px | paint-v2-0 completo | 82,1 s |

## Benchmark A1 e medição dos presets

1. Crie o contêiner de desenvolvimento, com o repositório em `/workspace`, caminho esperado pelos scripts de `benchmark/` e `validation/`.

```bash
sudo docker run -d --name cerise26_gen3d_dev --gpus all --ipc=host \
  -e HY3DGEN_MODELS=/workspace/hy3dgen_models -e TP=/workspace/third_party \
  -v ~/cerise2026/gen3d:/workspace -v ~/cerise2026/hf_cache:/root/.cache/huggingface \
  -w /workspace/benchmark cerise26_gen3d:latest sleep infinity
```

2. Valide as métricas com o autoteste (malha de referência transformada) e rode o modelo escolhido nos 13 objetos, gravando numa pasta nova para preservar os resultados de referência.

```bash
D="sudo docker exec cerise26_gen3d_dev"
$D python selftest_metrics.py && $D python evaluate.py --tags gt_selftest
$D python run_model.py --config hy2_turbo --out /workspace/results/repro
$D python evaluate.py --results /workspace/results/repro --tags hy2_turbo
$D python aggregate.py --bench /workspace/results/repro --tags hy2_turbo \
  --prefix repro --out /workspace/results/repro --resdir /workspace/results/repro
```

O `evaluate.py` alinha cada malha à referência (ICP com escala), calcula Chamfer e F-score e mede o CLIP nas vistas renderizadas; o `aggregate.py` gera `repro_tabela.csv`, `repro_tabela.md` e os gráficos. As configurações ficam em `CONFIGS`, no `benchmark/run_model.py` (`hy2_turbo`, `hy2mini_turbo`, `hy2_full`, `hy21_full`, `triposr`, `instantmesh` e outras); `--objects` aceita uma lista separada por vírgulas e `--override` altera parâmetros em JSON.

![Resultado de referência do benchmark A1: F-score e CLIP em função do tempo mediano por objeto, com o Hunyuan3D-2 Turbo como melhor compromisso](evidencias/a1_qualidade_vs_tempo.png)

3. TripoSR, InstantMesh e Hunyuan3D-2.1 precisam de dependências fora da imagem: clone-os em `third_party/` (commits em [`TERCEIROS.md`](TERCEIROS.md)) e rode, com `$D bash`, `/workspace/docker/install_stage2b.sh`, `/workspace/docker/install_stage3.sh` e `/workspace/docker/install_hy21.sh`.

4. Meça os *presets* no pipeline empacotado (13 objetos e 6 fotos CC0); a saída regrava `results/presets/`.

```bash
$D python run_presets.py --presets rapido,padrao
$D python run_presets.py --presets alto
$D python evaluate.py --results /workspace/results/presets \
  --tags preset_rapido,preset_padrao,preset_alto
```

## Testes funcionais A4

1. Rode a suíte pytest em duas partes, com cerca de 30 GB de memória livre. Ela verifica o glTF-Validator, a textura, a ausência de Draco, meshopt e KTX2, as faces, a caixa de 0,30 m e os limites de tempo e tamanho; a saída fica em `results/a4_pytest/`.

```bash
sudo docker exec -e GEN3D_TEST_PRESETS=rapido,padrao -e JUNIT_NAME=rapido_padrao \
  cerise26_gen3d_dev bash /workspace/validation/run_a4.sh pytest
sudo docker exec -e GEN3D_TEST_PRESETS=alto -e JUNIT_NAME=alto \
  cerise26_gen3d_dev bash /workspace/validation/run_a4.sh pytest
```

2. Para o carregamento no `<model-viewer>` e no three.js (Chromium via Playwright), instale as ferramentas que faltam e rode as etapas que usam `results/presets/`; elas regravam figuras de `evidencias/` (compare com `git diff --stat`).

```bash
D="sudo docker exec cerise26_gen3d_dev"
$D bash /workspace/docker/install_gltftools.sh
$D bash -c "pip install --no-cache-dir playwright \
  && python -m playwright install --with-deps chromium"
$D bash /workspace/validation/run_a4.sh viewer
$D bash /workspace/validation/run_a4.sh grids
```

## Servidor de geração 3D com fila

1. Construa a imagem do servidor e baixe o modelo de remoção de fundo do `rembg` 2.0.65, exigido por `scripts/start.sh`. O worker roda sem rede e com `HF_HUB_OFFLINE=1`; todos os pesos precisam estar no disco.

```bash
cd ~/cerise2026/gen3d/server
sudo docker build -t cerise26_gen3d_server:latest .
mkdir -p models/u2net
curl -L -o models/u2net/u2net.onnx \
  https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx
sha256sum models/u2net/u2net.onnx
```

O SHA-256 esperado é `8d10d2f3bb75ae3b6d527c77944fc5e7dcd94b29809d47a739a7a728a912b491`.

2. Ajuste os caminhos absolutos de `compose.yaml`, que apontam para a máquina original, e, se preciso, `GEN3D_CORS_ORIGINS` em `gen3d.env`.

```bash
sed -i "s#/home/[^/]*/cerise2026#$HOME/cerise2026#g" compose.yaml
grep -n cerise2026 compose.yaml
```

3. Suba, acompanhe e pare o serviço.

```bash
bash scripts/start.sh      # sobe API + worker e espera o /health "ok" (2 a 4 min)
bash scripts/status.sh     # contêineres, /health, fila, memória e GPU por processo
sudo docker logs -f cerise26_gen3d_worker1
bash scripts/stop.sh       # parada graciosa; a fila fica no SQLite em data/
```

A API escuta só em `127.0.0.1:8095`; o worker não tem rede. `bash scripts/start.sh 2` usa 2 *slots* com pesos compartilhados; `sudo touch data/PAUSE` drena a GPU sem derrubar a API; `bash scripts/redeploy.sh` reconstrói e recria tudo após mudanças no código. Os limites (fila de 32, até 4 pedidos em andamento por cliente, 6 envios por minuto por cliente e retenção de 7 dias) ficam em `gen3d.env` (`GEN3D_MAX_QUEUE`, `GEN3D_MAX_QUEUED_PER_CLIENT`, `GEN3D_RATE_JOBS_PER_MIN` e `GEN3D_RETENTION_DAYS`), descritos em [`server/README.md`](server/README.md).

4. Rode os 18 testes automatizados, com motor simulado e sem GPU.

```bash
bash scripts/run_pytest.sh
```

![Saída esperada de scripts/run_pytest.sh: 18 testes do servidor aprovados](evidencias/srv_term_pytest.png)

## Testes com curl, endpoint legado e aplicativo

1. Na máquina do servidor, teste o fluxo com curl, trocando `<id>` pelo `job_id` devolvido.

```bash
curl -s http://127.0.0.1:8095/api/v1/health
curl -s -F "image=@../validation/real/cc0_rooster.jpg" \
  -F 'options={"preset":"rapido","texture":true,"remove_background":true}' \
  http://127.0.0.1:8095/api/v1/jobs
curl -s http://127.0.0.1:8095/api/v1/jobs/<id>
curl -s -o model.glb http://127.0.0.1:8095/api/v1/jobs/<id>/model.glb
curl -s -F "front=@../validation/real/cc0_rooster.jpg" -F 'metadata={}' \
  -o objeto_ajustado.glb http://127.0.0.1:8095/
```

O envio responde `202` com `job_id`, `position` e `eta_seconds`; o estado vai de `queued` a `running` (com `progress` e `stage`) e a `done`; reenviar a mesma foto responde na hora com `"cached":true`. A última chamada usa o endpoint legado de 2025 (`POST /`), que devolve o GLB na resposta. `bash scripts/smoke.sh ../validation/real/cc0_rooster.jpg padrao` faz o ciclo completo; a documentação interativa fica em `http://127.0.0.1:8095/docs`.

2. De outro computador, abra um encaminhamento local de SSH, que não expõe nada, e, em outro terminal, rode o teste ponta a ponta a partir da pasta `server` de um clone (requer Python com `requests`).

```bash
ssh -N -L 127.0.0.1:18095:localhost:8095 <usuario>@<maquina-gpu>
python scripts/e2e_windows.py --base http://127.0.0.1:18095 \
  --photo ../validation/real/cc0_rooster.jpg --out e2e_out
python scripts/glb_check.py e2e_out/model.glb
```

O `e2e_windows.py` percorre health, envio, fila, downloads, conferência do GLB, cache, endpoint legado e erros de validação; o `glb_check.py` mostra a caixa em metros, o formato da textura e as extensões.

3. No aplicativo CERISE AR 1.1.0 (repositório `cerise-ar`, branch `feat/2026-gen3d-playstore`), abra Configurações, informe a URL do servidor e toque em Testar conexão. No emulador Android, use `http://10.0.2.2:18095` com o túnel acima (`10.0.2.2` é o computador hospedeiro). Depois, escolha uma foto, acompanhe a fila e abra o modelo em Meus modelos. Sem GPU, `node cerise-expo/tools/mock-gen3d-server.js --port 18096`, do mesmo repositório, simula o contrato `/api/v1`.

## Teste de carga

A suíte usa as 64 imagens de `server/loadtest/pool/`, do pacote `gen3d_servidor_brutos.tar.gz` ou geradas com `python3 loadtest/make_image_pool.py .. loadtest/pool` (requer Pillow). Com o servidor no ar:

```bash
cd ~/cerise2026/gen3d/server
bash loadtest/run_suite_new.sh
sudo docker stop cerise26_gen3d_worker1
bash loadtest/run_baseline.sh lock && bash loadtest/run_baseline.sh nolock
sudo docker start cerise26_gen3d_worker1
sudo docker run --rm -v "$PWD:/opt/gen3d/server" cerise26_gen3d_server:latest \
  python loadtest/analyze.py results/loadtest results/tabelas results/figuras
```

A suíte roda rajadas de 1 a 16 clientes com 1 e 2 *slots*, cache, coalescência, prioridade contra FIFO e *backpressure*, e no fim restaura a configuração de produção. O *baseline* reproduz o Flask síncrono de 2025 com o modelo real e exige o worker novo parado, por causa do teto de 24 GB.

## Exposição pública (opcional)

O servidor não foi exposto à internet no projeto. O [`server/README.md`](server/README.md) traz uma proposta, que só deve ser aplicada com autorização do responsável pela máquina de GPU e com estes cuidados:

- prefira uma VPN entre o *proxy* público e a máquina de GPU; túneis SSH reversos são frágeis, e túneis de terceiros fazem as fotos passarem por outra empresa (LGPD);
- aceite só HTTPS, com TLS no *proxy*;
- gere suas próprias chaves em `GEN3D_API_KEYS`, num arquivo `gen3d.secrets.env` fora do git, incluído no `env_file` da API; o app envia `X-API-Key` quando compilado com `EXPO_PUBLIC_GEN3D_API_KEY`, mas uma chave embutida no APK só filtra abuso;
- use `GEN3D_TRUST_PROXY=1` só atrás de um *proxy* que sobrescreva o `X-Forwarded-For`;
- publique só `/api/v1/*` (e `POST /`, se necessário), bloqueie `/metrics`, `/docs` e `/openapi.json`, limite o corpo a 16 MB e mantenha a fila máxima e o *rate limit*.

## Verificação do resultado

A máquina foi compartilhada com serviços de produção, e os tempos absolutos são limites superiores: o Hunyuan3D-2 Turbo levou 68,8 s por objeto sob carga plena e 28,7 s com a máquina parcialmente livre. As métricas de qualidade devem coincidir de perto.

**Tabela: Valores de referência medidos e arquivos em que estão registrados**

| Verificação | Valor de referência | Arquivo |
|---|---|---|
| Autoteste das métricas | Chamfer médio 0,0042; F@0,05 ≥ 0,976 | [`results/bench/gt_selftest/metrics.csv`](results/bench/gt_selftest/metrics.csv) |
| A1, Hunyuan3D-2 Turbo | Chamfer 0,032; F@0,05 0,951; F@0,1 0,992; CLIP entrada 0,907; CLIP vistas novas 0,854; pico 14,6 GB | [`resultados/a1_tabela.csv`](resultados/a1_tabela.csv) |
| Presets (medianas no GSO) | 23,9 s, 30,4 s e 82,1 s; pico 14,5 GB; carga 115 s e aquecimento 79 s | [`resultados/READY.json`](resultados/READY.json), [`resultados/presets_tabela.csv`](resultados/presets_tabela.csv) |
| A4 | 38 e 20 testes aprovados; 7 de 7 GLBs carregados | [`resultados/a4_pytest/`](resultados/a4_pytest/), [`resultados/viewer/viewer_report.json`](resultados/viewer/viewer_report.json) |
| Testes do servidor | 18 aprovados | [`server/resultados/pytest_server_spark.txt`](server/resultados/pytest_server_spark.txt) |
| Ponta a ponta (padrão) | GLB em 16,1 s; 20 mil triângulos; 0,72 MB; textura `image/jpeg`; maior dimensão 0,30 m | [`server/resultados/e2e/e2e_console.txt`](server/resultados/e2e/e2e_console.txt) |
| Carga, fila e 1 worker (33 jobs) | 33 de 33; p50 49,6 s e p95 174,1 s; 4,99 jobs/min com 16 clientes | [`server/resultados/tabelas/carga_resumo.md`](server/resultados/tabelas/carga_resumo.md) |
| Cache e *backpressure* | acerto em 0,02 s; fila máxima 8 e 16 clientes: 9 aceitos, 7 recusados com 429 | [`server/resultados/tabelas/carga_cenarios_extras.md`](server/resultados/tabelas/carga_cenarios_extras.md) |

Os tamanhos de GLB da rodada de *presets* (1,65, 2,01 e 6,14 MB) correspondem a texturas PNG, anteriores à correção do pós-processamento; com o código atual, saem bem menores (no padrão, a mesma foto passou de 2,97 MB para 0,72 MB).

![Resultado esperado do teste ponta a ponta: foto enviada, miniatura do servidor, GLB com textura JPEG no model-viewer e, à direita, o mesmo modelo antes da correção da textura](evidencias/srv_e2e_resultado.png)

## Problemas comuns e soluções

- **Worker em loop de reinício após desligamento abrupto.** O cache do numba gravado no contêiner corrompeu. Mantenha `NUMBA_CACHE_DIR=/tmp/numba_cache` em `gen3d.env` e o `tmpfs` de `compose.yaml`, veja `sudo docker logs --tail 50 cerise26_gen3d_worker1` e recrie os contêineres, pois reiniciá-los não basta: `sudo GEN3D_WORKER_SLOTS=1 GEN3D_TRUST_PROXY=0 docker compose -f compose.yaml up -d --force-recreate` (ou `bash scripts/redeploy.sh`).
- **GLB com textura PNG, maior que o esperado.** O `gltf-transform jpeg` 4.5 só recomprime texturas JPEG; o `pipeline/postprocess.py` atual passa `--formats "*"`. Reconstrua imagens antigas, confira `result.stats.texture_mime` e, sempre que a saída mudar, troque `GEN3D_PIPELINE_VERSION`, senão o cache devolve GLBs antigos.
- **Erro ao carregar o UNet do módulo de textura.** Rode de novo `make_local_tree.py` e `fix_turbo_unet.py`, com o cache em `/root/.cache/huggingface`.
- **Falta do modelo de remoção de fundo.** O `start.sh` acusa falta de `u2net.onnx` ou o worker tenta baixar pesos: o worker não tem rede, baixe tudo antes.
- **Worker não carrega o modelo ou não pega jobs.** Ele exige 10 GB de `MemAvailable` além do modelo (`GEN3D_MIN_AVAILABLE_GB`) e para enquanto existir `data/PAUSE`; sem o *preset* alto, economizam-se ~4,4 GB. Como o `compose.yaml` define `GEN3D_WORKER_PRESETS` no ambiente do worker, passe o valor na linha de comando, na pasta `server`: `sudo GEN3D_WORKER_SLOTS=1 GEN3D_TRUST_PROXY=0 GEN3D_WORKER_PRESETS=rapido,padrao docker compose -f compose.yaml up -d --force-recreate worker1`.
- **HTTP 429 em testes manuais.** Aguarde o `Retry-After` ou, só para testes, aumente `GEN3D_RATE_JOBS_PER_MIN`.
- **Falhas com gerações simultâneas.** O *scheduler* da difusão guarda estado; para concorrência, use os *slots* do worker, que têm travas por componente.
- **Modelos bloqueados no benchmark.** TRELLIS e TRELLIS.2 dependem de `spconv` e `cumm`, sem pacotes para aarch64; Stable Fast 3D e SPAR3D exigem aceite da licença no Hugging Face. Em x86_64, não foram testados.
- **Extração no Windows.** Use `tar --force-local -xzf` quando o caminho começar com a letra da unidade.

## Referências do repositório

- [`README.md`](README.md), [`RELEASES.md`](RELEASES.md) e [`TERCEIROS.md`](TERCEIROS.md): visão geral, pacotes com SHA-256 e componentes de terceiros.
- [`RELATORIO_SECAO.md`](RELATORIO_SECAO.md) e [`RELATORIO_SECAO_SERVIDOR.md`](RELATORIO_SECAO_SERVIDOR.md): metodologia e resultados completos.
- [`docker/Dockerfile`](docker/Dockerfile), [`models/download_weights.py`](models/download_weights.py), [`models/make_local_tree.py`](models/make_local_tree.py) e [`models/fix_turbo_unet.py`](models/fix_turbo_unet.py): imagem e pesos.
- [`pipeline/gen3d_pipeline.py`](pipeline/gen3d_pipeline.py), [`pipeline/presets.json`](pipeline/presets.json) e [`pipeline/postprocess.py`](pipeline/postprocess.py): pipeline.
- [`benchmark/run_model.py`](benchmark/run_model.py), [`benchmark/evaluate.py`](benchmark/evaluate.py), [`benchmark/aggregate.py`](benchmark/aggregate.py) e [`benchmark/run_presets.py`](benchmark/run_presets.py): benchmark.
- [`validation/test_pipeline.py`](validation/test_pipeline.py) e [`validation/run_a4.sh`](validation/run_a4.sh): validação A4.
- [`server/README.md`](server/README.md), [`server/compose.yaml`](server/compose.yaml), [`server/gen3d.env`](server/gen3d.env), [`server/scripts/`](server/scripts/), [`server/tests/test_api.py`](server/tests/test_api.py) e [`server/loadtest/`](server/loadtest/): servidor.

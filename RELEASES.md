# Artefatos grandes (Releases)

Os GLBs gerados, as renderizações usadas nas métricas, os dados de avaliação e as saídas brutas do servidor somam
~1,9 GB descompactados e ficam fora do git, em arquivos `.tar.gz` anexados ao Release **`dados-2026-10-26`** deste
repositório. Todos os pacotes usam caminhos relativos à raiz do repositório: extraídos nela, recriam as pastas exatamente
como estavam no DGX Spark (`~/cerise2026/gen3d`) e no Windows, ao lado dos arquivos de métricas que já estão no git.
Nenhum pacote passa de 1,9 GB, por isso não há partes divididas. Os pacotes 1–6 foram gerados no Spark por
[`scripts/empacotar_releases.sh`](scripts/empacotar_releases.sh) em 26/10/2026; o pacote 7, no Windows.

| # | arquivo | tamanho | arquivos (GLB / imagens) | SHA-256 | conteúdo |
|---|---|---|---|---|---|
| 1 | `gen3d_results_bench.tar.gz` | 194,1 MB (261,3 MB descompactado) | 649 (98 / 355) | `005730f789e9d0819d315c23687e350f71a1dc6f2470bfb44313962bd0afef0e` | `results/bench/`: benchmark A1 — GLB/OBJ de cada modelo e objeto (TripoSR, InstantMesh, Hunyuan3D-2mini-Turbo, 2-Turbo, 2.0, 2.1 PBR, tentativas `*_t1`), renderizações az 030/120/210/300, `metrics.csv`, `summary.json`, autoteste `gt_selftest/` |
| 2 | `gen3d_results_a3_a3i.tar.gz` | 330,7 MB (362,8 MB) | 703 (105 / 376) | `2ec41765f51497407e1fab3416b96883530b47c432962d9fc6d6941f8fa5ed8b` | `results/a3/` (10 variantes, série sequencial, 7 objetos) e `results/a3i/` (série intercalada, 4 objetos): GLBs, renderizações e métricas |
| 3 | `gen3d_results_presets.tar.gz` | 639,8 MB (688,0 MB) | 545 (228 / 213) | `ef8591e9bdfd1c4be96e5b3c332dca7770e8284359b6864ee4797dbc232f050e` | `results/presets/`: presets rápido, padrão e alto no pipeline empacotado (13 GSO + 6 fotos CC0): GLB final, intermediários, miniatura, renderizações, `stats.json`, `pipeline_load_*.json` |
| 4 | `gen3d_results_a4_test.tar.gz` | 106,9 MB (119,1 MB) | 91 (41 / 25) | `71b0ff1c00528bf44476bf65f5892417f228e507a19b9f1c24cef701225c7440` | `results/a4_pytest/` (GLBs gerados pela suíte pytest A4, saídas e JUnit) e `results/test/` (testes iniciais: comparação de compressão Draco/meshopt/sem compressão, TripoSR, Hunyuan3D-2, grades) |
| 5 | `gen3d_dados_gso_cc0.tar.gz` | 201,3 MB (332,7 MB) | 282 (0 / 175) | `cd43aa510feba365fcfffb6f871c853b0daf5d589d8f15efc9ea51d48e7f016f` | `data/`: 13 objetos originais do Google Scanned Objects (CC-BY 4.0), renderizações de avaliação (`eval/`: entrada, vistas de referência, malha normalizada e nuvem de pontos), 6 fotos CC0 e `gso_names.txt` — atribuição em [`data/README.md`](data/README.md) |
| 6 | `gen3d_servidor_brutos.tar.gz` | 101,8 MB (112,2 MB) | 209 (55 / 83) | `f0f080c0bdd90dd180eca4b5b9f954464176a4aa5e7f8194f6fadef60ef877a5` | `server/results/` (resultados brutos da carga, GLBs das rodadas de 2025 com e sem trava, ponta a ponta, logs de reimplantação), `server/data/` (cópia consistente do banco SQLite feita com a API de *backup*, registros `jobs_q*.json` e 16 jobs de teste com `model.glb`, miniatura e `stats.json`; as fotos de entrada já tinham sido apagadas pelo próprio servidor), `server/loadtest/pool/` (64 imagens de entrada da carga, derivadas do GSO e das fotos CC0) e `server/results_baseline_run.log` |
| 7 | `gen3d_servidor_e2e_windows.tar.gz` | 7,2 MB (8,0 MB) | 14 (6 / 3) | `06ad6fc3f373ca97fb0443d502ba5767ec39e10cc31cf05acc0226ab9a07461e` | `server/e2e_out*/`: GLBs, miniaturas e `e2e_resultado.json` baixados no Windows nos testes ponta a ponta (antes da correção da textura, versão corrigida e versão final no preset rápido) e `server/e2e_out_console.txt` |

O banco do servidor guarda só o *hash* do cliente (nunca o IP); nenhum pacote contém dados pessoais, credenciais ou
pesos de terceiros.

## Como baixar e extrair

```bash
# na raiz de um clone deste repositório (substituir cerise-ufg pelo nome da organização)
gh release download dados-2026-10-26 -R cerise-ufg/cerise-2026-gen3d -D _releases
cd _releases && sha256sum -c SHA256SUMS && cd ..
for f in _releases/gen3d_*.tar.gz; do tar -xzf "$f"; done
```

No Windows (Git Bash), use `tar --force-local -xzf` quando o caminho do arquivo começar com a letra da unidade
(`C:/...`). Os arquivos extraídos caem em caminhos ignorados pelo `.gitignore` (`*.glb`, `results/**/*.png`,
`data/gso/`, `server/data/`, ...), então o `git status` continua limpo. O arquivo `SHA256SUMS` publicado no Release
contém as mesmas somas da tabela acima.

## Publicação (mantenedor)

```bash
cd <pasta com os pacotes>
gh release create dados-2026-10-26 -R cerise-ufg/cerise-2026-gen3d \
  --title "Dados e saídas brutas — 26/10/2026" --notes "Ver RELEASES.md" \
  gen3d_*.tar.gz SHA256SUMS
```

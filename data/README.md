# Dados de avaliação (`data/`)

Cópia da pasta `~/cerise2026/gen3d/data` do DGX Spark. No git ficam só os índices e metadados; os arquivos binários
estão no pacote `gen3d_dados_gso_cc0.tar.gz` dos Releases (ver [`../RELEASES.md`](../RELEASES.md)), que extraído na
raiz do repositório recria exatamente esta pasta.

| caminho | no git | no Release | conteúdo |
|---|---|---|---|
| `gso_names.txt` | sim | sim | lista de modelos do owner `GoogleResearch` no Gazebo Fuel (gerada por `benchmark/gso_list.sh`) |
| `gso/<objeto>/` | não | sim | 13 objetos originais do Google Scanned Objects (`meshes/model.obj`, `.mtl`, `texture.png`, `model.config`, `metadata.pbtxt`), baixados por `benchmark/gso_download.sh` |
| `eval/index.json`, `eval/<objeto>/info.json` | sim | sim | faces, vértices, tamanho original (m) e escala de normalização de cada objeto |
| `eval/<objeto>/input.png`, `input_white.png` | não | sim | vista de entrada (azimute 30°) com alfa e sobre fundo branco |
| `eval/<objeto>/gt_view_az{030,120,210,300}.png` | não | sim | vistas de referência usadas no CLIP de vistas novas |
| `eval/<objeto>/gt_norm.ply`, `gt_points.npy` | não | sim | malha de referência normalizada e nuvem de pontos amostrada (Chamfer/F-score) |
| `real/*.jpg`, `real/fontes.json` | só `fontes.json` (as fotos estão em `validation/real/`) | sim | 6 fotos reais CC0 |

Os arquivos de `eval/` são gerados por `benchmark/prepare_gso.py` a partir de `gso/` (renderização com nvdiffrast).

## Atribuição e licenças

* **Google Scanned Objects** — Google Research, distribuído pelo Gazebo Fuel (owner `GoogleResearch`), licença
  **Creative Commons Attribution 4.0 International (CC-BY 4.0)**, https://creativecommons.org/licenses/by/4.0/.
  Referência: L. Downs et al., "Google Scanned Objects: A High-Quality Dataset of 3D Scanned Household Items",
  IEEE ICRA 2022. Objetos usados: Schleich_Bald_Eagle, Schleich_African_Black_Rhino, Sonny_School_Bus,
  Threshold_Porcelain_Teapot_White, Crosley_Alarm_Clock_Vintage_Metal, Android_Figure_Panda,
  ACE_Coffee_Mug_Kristen_16_oz_cup, Schleich_Lion_Action_Figure, Breyer_Horse_Of_The_Year_2015, Reebok_ZIGLITE_RUSH,
  Vtech_Roll_Learn_Turtle, Vtech_Stack_Sing_Rings_636_Months, Transformers_Age_of_Extinction_Mega_1Step_Bumblebee_Figure.
  Modificações feitas aqui: cópia de `texture.png` para junto da malha e, em `eval/`, normalização de escala e
  renderizações derivadas.
* **Fotos reais** — Wikimedia Commons / The Metropolitan Museum of Art Open Access, domínio público (**CC0**); título,
  página e URL de cada foto em `real/fontes.json` (idêntico a `validation/real/fontes.json`).

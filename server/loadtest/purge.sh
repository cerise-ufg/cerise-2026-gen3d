#!/usr/bin/env bash
# Apaga jobs/arquivos entre rodadas do teste de carga (zera o cache), mantendo API e worker no ar.
sudo docker exec cerise26_gen3d_api python -m cerise_gen3d_server.manage purge --yes

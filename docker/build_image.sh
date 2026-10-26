#!/bin/bash
# (host Spark) constroi cerise26_gen3d:latest limitado a 4 nucleos (builder classico permite --cpuset-cpus),
# para nao competir com os jobs de producao/benchmark.
cd ~/cerise2026/gen3d
LOG=~/cerise2026/gen3d/logs/docker_build.log
echo "inicio $(date -u +%FT%TZ)" > $LOG
DOCKER_BUILDKIT=0 sudo -E docker build --cpuset-cpus=16-19 -f docker/Dockerfile -t cerise26_gen3d:latest . >> $LOG 2>&1
echo "RC=$? fim $(date -u +%FT%TZ)" >> $LOG
sudo docker images cerise26_gen3d --format '{{.Repository}}:{{.Tag}} {{.Size}} {{.CreatedAt}}' >> $LOG

#!/bin/bash
# (host Spark) Fila "protegida" da frente gen3d, depois que a producao (vLLM) religou:
#  - um job de GPU por vez;
#  - antes de cada job espera MemAvailable >= (memoria do job + 10 GB) e vLLM estavel (sem reinicio por 60 s);
#  - durante o job, se algum vllm-* mudar de estado/reiniciar, interrompe o job, registra e segue (apos estabilizar)
#    com a configuracao reduzida (quando houver) ou pula.
C=cerise26_gen3d_dev
LOG=~/cerise2026/gen3d/logs/chain_guarded.log
E="sudo docker exec -e HY3DGEN_MODELS=/workspace/hy3dgen_models -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True -w /workspace/benchmark $C"
log() { echo "$(date -u +%FT%TZ) $*" | tee -a $LOG; }
avail() { awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo; }
vstate() { for c in vllm-server vllm-embed vllm-stt; do sudo docker inspect -f '{{.Name}}={{.State.Status}}@{{.State.StartedAt}}' $c 2>/dev/null; done | tr '\n' ' '; }

wait_ok() {  # wait_ok <GB do job> <timeout_s>
  local need=$1 to=${2:-100000} t0=$(date +%s) a s1 s2
  while true; do
    a=$(avail); s1=$(vstate)
    if [[ "$s1" != *exited* && "$s1" != *restarting* ]] && [ "$a" -ge $((need + 10)) ]; then
      sleep 60; s2=$(vstate)
      if [ "$s1" == "$s2" ] && [ "$(avail)" -ge $((need + 10)) ]; then return 0; fi
    fi
    if [ $(( $(date +%s) - t0 )) -gt $to ]; then log "TIMEOUT aguardando memoria (precisa $((need + 10)) GB, available=${a} GB)"; return 1; fi
    log "aguardando: available=${a}GB precisa=$((need + 10))GB vllm=[$s1]"; sleep 60
  done
}

run_job() {  # run_job <nome> <GB> <timeout_espera_s> <comando> [comando_reduzido]
  local name=$1 need=$2 to=$3 cmd=$4 small=$5 s0 s pid
  wait_ok $need $to || { log "PULADO $name"; return 2; }
  s0=$(vstate)
  log "inicio $name (available=$(avail)GB)"
  $E bash -c "$cmd" &
  pid=$!
  while kill -0 $pid 2>/dev/null; do
    sleep 20
    s=$(vstate)
    if [ "$s" != "$s0" ]; then
      log "vLLM mudou durante $name: [$s0] -> [$s] -> interrompendo o job"
      sudo docker exec $C pkill -f "^python " ; wait $pid
      if [ -n "$small" ]; then
        log "repetindo $name com configuracao reduzida apos estabilizar"
        run_job "${name}_reduzido" $need $to "$small"
      fi
      return 1
    fi
  done
  wait $pid; local rc=$?
  log "fim $name rc=$rc (available=$(avail)GB)"
  return 0
}

S4=Schleich_Bald_Eagle,Sonny_School_Bus,ACE_Coffee_Mug_Kristen_16_oz_cup,Vtech_Roll_Learn_Turtle
S7=Schleich_Bald_Eagle,Schleich_African_Black_Rhino,Sonny_School_Bus,Threshold_Porcelain_Teapot_White,ACE_Coffee_Mug_Kristen_16_oz_cup,Transformers_Age_of_Extinction_Mega_1Step_Bumblebee_Figure,Vtech_Roll_Learn_Turtle
L=/workspace/logs

log "=== fila protegida iniciada; vllm=[$(vstate)] available=$(avail)GB"
run_job a3_intercalado 15 3600 \
  "python a3_interleaved.py --objects $S4 --variants i_base,i_fastpost,i_oct256,i_faces20k,i_faces10k,i_tex1024,i_steps10 > $L/a3/interleaved.log 2>&1" \
  "python a3_interleaved.py --objects Schleich_Bald_Eagle,Sonny_School_Bus --variants i_base,i_fastpost,i_oct256,i_faces20k,i_tex1024 > $L/a3/interleaved.log 2>&1"
run_job presets_rapido_padrao 15 3600 "python run_presets.py --presets rapido,padrao > $L/presets_rp.log 2>&1"
run_job presets_alto 16 3600 "python run_presets.py --presets alto > $L/presets_alto.log 2>&1"
run_job eval_presets 4 3600 "python evaluate.py --results /workspace/results/presets --tags preset_rapido,preset_padrao,preset_alto > $L/eval_presets.log 2>&1"
run_job hy2_full_4obj 15 3600 \
  "python run_model.py --config hy2_full --objects $S4 --out /workspace/results/bench > $L/a1/hy2_full.log 2>&1" \
  "python run_model.py --config hy2_full --objects Sonny_School_Bus,Vtech_Roll_Learn_Turtle --out /workspace/results/bench > $L/a1/hy2_full.log 2>&1"
run_job a3_bf16 14 3600 \
  "mv -n $L/a3/a3_bf16.log $L/a3/a3_bf16_falha_numpy.log; python run_model.py --config hy2_turbo --override '{\"shape_dtype\": \"bf16\"}' --tag a3_bf16 --objects $S7 --out /workspace/results/a3 > $L/a3/a3_bf16.log 2>&1"
run_job hy21_full_2obj 14 3600 \
  "python run_model.py --config hy21_full --objects ACE_Coffee_Mug_Kristen_16_oz_cup,Sonny_School_Bus --out /workspace/results/bench > $L/a1/hy21_full.log 2>&1"
run_job instantmesh_v2 24 1200 \
  "python run_model.py --config instantmesh --out /workspace/results/bench > $L/a1/instantmesh.log 2>&1"
run_job eval_final 4 3600 "python evaluate.py --tags hy2_full,hy21_full,instantmesh --skip-existing > $L/eval_final_a1.log 2>&1; python evaluate.py --results /workspace/results/a3 --tags a3_bf16,a3_noflashvdm --skip-existing > $L/eval_final_a3.log 2>&1; python evaluate.py --results /workspace/results/a3i --tags i_base,i_fastpost,i_oct256,i_faces20k,i_faces10k,i_tex1024,i_steps10 > $L/eval_a3i.log 2>&1"
log "=== FILA_PROTEGIDA_FIM"

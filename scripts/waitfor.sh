#!/bin/bash
# waitfor.sh <arquivo> <regex> [timeout_s] [regex_saida]  -> espera o regex aparecer e mostra as linhas relevantes
F=$1; RE=$2; TO=${3:-540}; OUT=${4:-"ok=|aquecimento|Error|Traceback|FIM"}
timeout $TO bash -c "until grep -qE '$RE' '$F' 2>/dev/null; do sleep 15; done"
grep -E "$OUT" "$F" | cut -c1-420 | tail -${N:-6}

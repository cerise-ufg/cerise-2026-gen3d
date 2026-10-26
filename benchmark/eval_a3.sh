#!/bin/bash
# avalia e agrega as variantes A3 indicadas (uso: eval_a3.sh tag1,tag2,...)
cd /workspace/benchmark
python evaluate.py --results /workspace/results/a3 --tags "$1" --skip-existing > /workspace/logs/eval_a3.log 2>&1
python aggregate_a3.py --tags "$1" 2>&1 | grep -E "^\|"

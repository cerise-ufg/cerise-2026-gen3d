#!/bin/bash
# avalia e agrega o A3 intercalado
cd /workspace/benchmark
T=i_base,i_fastpost,i_oct256,i_faces20k,i_faces10k,i_tex1024,i_steps10
python evaluate.py --results /workspace/results/a3i --tags $T --skip-existing > /workspace/logs/eval_a3i_mine.log 2>&1
python - <<'EOF'
import sys
sys.path.insert(0, "/workspace/benchmark")
import aggregate as AG, aggregate_a3 as A3
lab = {"i_base": "base (turbo, oct 384, 40k, tex 2048, pymeshlab)", "i_fastpost": "pós-proc. rápido (sem pymeshlab)",
       "i_oct256": "octree 256", "i_faces20k": "20k faces", "i_faces10k": "10k faces", "i_tex1024": "textura 1024",
       "i_steps10": "10 passos (forma)", "i_rapido": "combinação 'rápido'", "i_padrao": "combinação 'padrão'"}
AG.LABELS.update(lab)
S = []
for t in "i_base,i_fastpost,i_oct256,i_faces20k,i_faces10k,i_tex1024,i_steps10".split(","):
    try:
        S.append(AG.summarize(t, *AG.load("/workspace/results/a3i", t)))
    except FileNotFoundError as e:
        print("ignorado", t, e)
AG.write_tables(S, "a3i", "/workspace/resultados")
base = [s for s in S if s["tag"] == "i_base"][0]
AG.plot_stages(S, "/workspace/evidencias/a3i_tempo_por_etapa.png",
               "A3 intercalado — Hunyuan3D-2 Turbo, 4 objetos GSO: tempo médio por etapa")
A3.plot_quality(S, base, "/workspace/evidencias/a3i_qualidade_variantes.png", "A3 intercalado — qualidade por variante")
EOF

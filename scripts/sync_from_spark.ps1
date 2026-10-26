# Traz do Spark para o espelho local: codigo, resultados leves (json/csv/png) e evidencias. Nao traz pesos nem GLBs grandes.
$ErrorActionPreference = "Continue"
$L = "E:/CERISE/FRENTES/REALIDADE AUMENTADA/GERACAO_3D"
$R = "spark-bridge:cerise2026/gen3d"
ssh spark-bridge "cd ~/cerise2026/gen3d && rm -f /tmp/gen3d_light.tgz && tar czf /tmp/gen3d_light.tgz --exclude='*.glb' --exclude='*.obj' --exclude='*.npy' --exclude='*.ply' --exclude='white_mesh*' --exclude='*.jpg.tmp*' evidencias resultados results/bench/*/summary.json results/bench/*/metrics.csv results/a3/*/summary.json results/a3/*/metrics.csv results/presets/*/summary.json results/presets/*/metrics.csv results/presets/pipeline_load.json results/a4_pytest logs/a1 logs/a3 READY.json 2>/dev/null; ls -la /tmp/gen3d_light.tgz"
scp spark-bridge:/tmp/gen3d_light.tgz "$env:TEMP/gen3d_light.tgz"
tar xzf "$env:TEMP/gen3d_light.tgz" -C $L

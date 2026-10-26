| config | jobs | ok | taxa_erro | lat_p50 | lat_p95 | lat_p99 | vazao_16_jobs_min | gpu_pico_gb | mem_disp_min_gb | respostas_trocadas |
|---|---|---|---|---|---|---|---|---|---|---|
| 2025: Flask síncrono, sem trava | 33 | 3 | 0.909 | 12.3 | 12.5 | 12.5 | 0.0 | 19.2 | 35.3 | 0 |
| 2025: Flask síncrono, com trava | 33 | 33 | 0.0 | 52.1 | 199.0 | 215.7 | 4.37 | 18.2 | 29.8 | 0 |
| 2026: fila + 1 worker | 33 | 33 | 0.0 | 49.6 | 174.1 | 188.8 | 4.99 | 22.9 | 29.1 | 0 |
| 2026: fila + 2 slots (pesos compartilhados) | 33 | 33 | 0.0 | 46.5 | 155.6 | 167.8 | 5.63 | 18.5 | 39.7 | 0 |

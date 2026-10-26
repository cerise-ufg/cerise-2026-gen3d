"""CERISE 2026 - servidor de geracao 3D (imagem -> GLB texturizado) para o app de RA.

Componentes:
  api.py     FastAPI (HTTP, validacao, fila, cache, rate limit, metricas, endpoint legado de 2025)
  worker.py  processo de GPU com o modelo quente (Gen3DPipeline), consome a fila persistente (SQLite)
  db.py      armazenamento persistente dos jobs (SQLite em modo WAL)
"""
__version__ = "1.0.0"

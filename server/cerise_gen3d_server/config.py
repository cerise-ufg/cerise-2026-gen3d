"""Configuracao por variaveis de ambiente (12-factor). Todos os valores tem padrao seguro para a rede interna."""
from __future__ import annotations

import os


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _int(name: str, default: int) -> int:
    return int(_env(name, str(default)))


def _float(name: str, default: float) -> float:
    return float(_env(name, str(default)))


def _bool(name: str, default: bool) -> bool:
    return _env(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "sim", "on")


def _list(name: str, default: str) -> list[str]:
    return [x.strip() for x in _env(name, default).split(",") if x.strip()]


class Settings:
    def __init__(self):
        # armazenamento (volume compartilhado entre API e workers)
        self.data_dir = _env("GEN3D_DATA_DIR", "/data")
        self.db_path = _env("GEN3D_DB", os.path.join(self.data_dir, "gen3d.sqlite3"))
        self.jobs_dir = os.path.join(self.data_dir, "jobs")

        # presets aceitos pela API e prioridade (deslocamento em segundos na ordenacao da fila:
        # score = criado_em + deslocamento -> FIFO com prioridade e envelhecimento; um job "alto" espera no
        # maximo `offset` segundos a mais do que esperaria numa FIFO pura, entao nao ha inanicao)
        self.presets = _list("GEN3D_PRESETS", "rapido,padrao,alto")
        offs = _list("GEN3D_PRIORITY_OFFSETS", "rapido:0,padrao:30,alto:90")
        self.priority_offsets = {k: float(v) for k, v in (x.split(":") for x in offs)}
        # estimativa inicial de duracao por preset (s) = medianas medidas no pipeline empacotado (READY.json);
        # depois e atualizada por media movel exponencial com os jobs reais
        ests = _list("GEN3D_EST_SECONDS", "rapido:24,padrao:30,alto:82")
        self.est_seconds = {k: float(v) for k, v in (x.split(":") for x in ests)}
        tos = _list("GEN3D_JOB_TIMEOUTS", "rapido:240,padrao:300,alto:600")
        self.job_timeouts = {k: float(v) for k, v in (x.split(":") for x in tos)}
        self.max_attempts = _int("GEN3D_MAX_ATTEMPTS", 2)

        # backpressure e limites
        self.max_queue = _int("GEN3D_MAX_QUEUE", 32)                 # jobs na fila -> 429 acima disso
        self.max_queued_per_client = _int("GEN3D_MAX_QUEUED_PER_CLIENT", 4)
        self.queue_timeout_s = _float("GEN3D_QUEUE_TIMEOUT_S", 3600)  # job esquecido na fila vira erro
        self.max_upload_bytes = _int("GEN3D_MAX_UPLOAD_BYTES", 15 * 1024 * 1024)
        self.max_pixels = _int("GEN3D_MAX_PIXELS", 50_000_000)        # protecao contra "decompression bomb"
        self.min_side = _int("GEN3D_MIN_SIDE", 64)
        self.norm_max_side = _int("GEN3D_NORM_MAX_SIDE", 2048)        # foto normalizada antes da fila

        # rate limit por cliente (token bucket): envios de job e leituras
        self.rate_jobs_per_min = _float("GEN3D_RATE_JOBS_PER_MIN", 6)
        self.rate_jobs_burst = _float("GEN3D_RATE_JOBS_BURST", 6)
        self.rate_reads_per_min = _float("GEN3D_RATE_READS_PER_MIN", 1200)
        self.rate_reads_burst = _float("GEN3D_RATE_READS_BURST", 200)
        self.trust_proxy = _bool("GEN3D_TRUST_PROXY", False)          # usar X-Forwarded-For (so atras do Caddy)

        # autenticacao opcional por chave (desligada na rede interna; ver proposta de exposicao no README)
        self.api_keys = set(_list("GEN3D_API_KEYS", ""))

        # cache por hash do conteudo
        self.cache_enabled = _bool("GEN3D_CACHE", True)
        self.pipeline_version = _env("GEN3D_PIPELINE_VERSION", "hy2turbo-a3-v2-jpeg")

        # retencao (politica de privacidade do app: fotos e modelos apagados em ate 7 dias)
        self.retention_days = _float("GEN3D_RETENTION_DAYS", 7)
        self.delete_input_after = _bool("GEN3D_DELETE_INPUT_AFTER_PROCESSING", True)
        self.janitor_interval_s = _float("GEN3D_JANITOR_INTERVAL_S", 300)

        # CORS (o app nativo nao precisa; vale para o visualizador web)
        self.cors_origins = _list("GEN3D_CORS_ORIGINS",
                                  "https://cerise.wenfur.com.br,http://localhost:8081,http://localhost:19006")

        # endpoint legado do app Android de 2025 (POST / sincrono)
        self.legacy_preset = _env("GEN3D_LEGACY_PRESET", "rapido")
        self.legacy_timeout_s = _float("GEN3D_LEGACY_TIMEOUT_S", 290)  # OkHttp do app 2025: readTimeout 5 min

        # worker
        self.worker_id = _env("GEN3D_WORKER_ID", "worker1")
        self.worker_slots = _int("GEN3D_WORKER_SLOTS", 1)
        self.worker_presets = _list("GEN3D_WORKER_PRESETS", "rapido,padrao,alto")
        self.warmup_presets = _list("GEN3D_WARMUP_PRESETS", "rapido")
        self.gpu_cap_gb = _float("GEN3D_GPU_CAP_GB", 24.0)
        self.min_available_gb = _float("GEN3D_MIN_AVAILABLE_GB", 10.0)  # regra do Spark: folga de memoria
        self.heartbeat_s = _float("GEN3D_HEARTBEAT_S", 5.0)
        self.worker_stale_s = _float("GEN3D_WORKER_STALE_S", 30.0)
        self.poll_interval_s = _float("GEN3D_POLL_INTERVAL_S", 0.25)
        self.fake_engine = _bool("GEN3D_FAKE_ENGINE", False)           # testes sem GPU
        self.fake_seconds = _float("GEN3D_FAKE_SECONDS", 1.0)
        self.model_name = _env("GEN3D_MODEL_NAME",
                               "Hunyuan3D-2 Turbo (dit-v2-0-turbo + FlashVDM, paint-v2-0-turbo; alto: paint-v2-0)")


settings = Settings()


def reload_settings() -> Settings:
    global settings
    settings = Settings()
    return settings

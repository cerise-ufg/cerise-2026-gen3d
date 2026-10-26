"""Utilitarios compartilhados: logs estruturados (JSON), hash de cliente, validacao/normalizacao da imagem,
rate limit (token bucket)."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import sys
import threading
import time

# --------------------------------------------------------------------------------------------- logs JSON


class JsonFormatter(logging.Formatter):
    RESERVED = set(vars(logging.LogRecord("x", 0, "", 0, "", None, None))) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        d = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k not in self.RESERVED and not k.startswith("_"):
                d[k] = v
        if record.exc_info:
            d["exc"] = self.formatException(record.exc_info)
        return json.dumps(d, ensure_ascii=False, default=str)


def setup_logging(name: str, level: str = "INFO") -> logging.Logger:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [h]
    root.setLevel(level)
    for noisy in ("uvicorn.access",):  # o acesso e registrado pelo middleware (JSON, com rota e duracao)
        logging.getLogger(noisy).handlers[:] = []
        logging.getLogger(noisy).propagate = False
    for n in ("uvicorn", "uvicorn.error"):
        logging.getLogger(n).handlers[:] = []
        logging.getLogger(n).propagate = True
    return logging.getLogger(name)


def client_hash(raw: str) -> str:
    """Identificador do cliente sem guardar o IP em claro (LGPD): sha256 truncado."""
    return hashlib.sha256(("cerise-gen3d|" + raw).encode()).hexdigest()[:16]


# --------------------------------------------------------------------------------------------- imagem
class ImageError(ValueError):
    pass


def normalize_image(data: bytes, max_pixels: int, min_side: int, max_side: int) -> tuple[bytes, dict]:
    """Valida (JPEG/PNG real, nao so a extensao), aplica a orientacao EXIF, remove metadados (EXIF/GPS),
    reduz para `max_side` e devolve um PNG (RGB ou RGBA, preservando a transparencia)."""
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = max_pixels
    try:
        probe = Image.open(io.BytesIO(data))
        fmt = probe.format
        probe.verify()
    except Image.DecompressionBombError as e:  # type: ignore[attr-defined]
        raise ImageError(f"imagem grande demais em pixels (limite {max_pixels // 1_000_000} MP)") from e
    except Exception as e:  # noqa: BLE001
        raise ImageError("arquivo não é uma imagem JPEG/PNG válida") from e
    if fmt not in ("JPEG", "PNG", "MPO"):
        raise ImageError(f"formato {fmt} não suportado (use JPEG ou PNG)")
    try:
        im = Image.open(io.BytesIO(data))
        w0, h0 = im.size
        if w0 * h0 > max_pixels:
            raise ImageError(f"imagem grande demais em pixels (limite {max_pixels // 1_000_000} MP)")
        if min(w0, h0) < min_side:
            raise ImageError(f"imagem pequena demais ({w0}x{h0}); mínimo {min_side} px no menor lado")
        im = ImageOps.exif_transpose(im)
        has_alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
        im = im.convert("RGBA" if has_alpha else "RGB")
        if max(im.size) > max_side:
            s = max_side / max(im.size)
            im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="PNG")  # sem EXIF: a localizacao GPS da foto nao fica no servidor
    except ImageError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ImageError(f"falha ao decodificar a imagem: {e}") from e
    return buf.getvalue(), {"format": fmt, "orig_w": w0, "orig_h": h0, "w": im.width, "h": im.height,
                            "alpha": has_alpha}


# --------------------------------------------------------------------------------------------- rate limit
class TokenBucket:
    """Rate limit por cliente em memoria (a API roda em um unico processo uvicorn)."""

    def __init__(self, rate_per_min: float, burst: float):
        self.rate = rate_per_min / 60.0
        self.burst = burst
        self._b: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, cost: float = 1.0) -> tuple[bool, float]:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._b.get(key, (self.burst, now))
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            if tokens >= cost:
                self._b[key] = (tokens - cost, now)
                return True, 0.0
            self._b[key] = (tokens, now)
            retry = (cost - tokens) / self.rate if self.rate > 0 else 60.0
            if len(self._b) > 50_000:  # limpeza de chaves antigas
                cutoff = now - 3600
                self._b = {k: v for k, v in self._b.items() if v[1] > cutoff}
            return False, retry

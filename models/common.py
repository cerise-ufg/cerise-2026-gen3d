"""Utilitarios comuns aos executores de modelos: cronometro por etapa, memoria de GPU, limite de memoria."""
from __future__ import annotations

import contextlib
import json
import os
import time

import torch

GPU_CAP_GB = float(os.environ.get("CERISE_GPU_CAP_GB", "24"))


def apply_gpu_cap(cap_gb: float = GPU_CAP_GB):
    """Limita a memoria do alocador do PyTorch (memoria unificada do GB10 e compartilhada com a producao)."""
    if not torch.cuda.is_available():
        return
    total = torch.cuda.get_device_properties(0).total_memory
    frac = min(1.0, cap_gb * 1024 ** 3 / total)
    torch.cuda.set_per_process_memory_fraction(frac, 0)
    return frac


class StageTimer:
    def __init__(self):
        self.t = {}

    @contextlib.contextmanager
    def __call__(self, name):
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        try:
            yield
        finally:
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            self.t[name] = self.t.get(name, 0.0) + time.perf_counter() - t0

    def total(self):
        return sum(self.t.values())


def gpu_reset_peak():
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()


def gpu_peak_gb():
    if not torch.cuda.is_available():
        return 0.0, 0.0
    return torch.cuda.max_memory_allocated() / 1024 ** 3, torch.cuda.max_memory_reserved() / 1024 ** 3


def gpu_now_gb():
    if not torch.cuda.is_available():
        return 0.0
    return torch.cuda.memory_allocated() / 1024 ** 3


def mesh_stats(glb_path):
    import trimesh
    scene = trimesh.load(glb_path, force="scene", process=False)
    nf = sum(len(g.faces) for g in scene.geometry.values() if hasattr(g, "faces"))
    nv = sum(len(g.vertices) for g in scene.geometry.values() if hasattr(g, "vertices"))
    return dict(faces=int(nf), vertices=int(nv), size_bytes=int(os.path.getsize(glb_path)))


def dump_json(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)

"""Operacao: python -m cerise_gen3d_server.manage <comando>

  stats              resumo da fila/jobs/workers
  cleanup            roda a limpeza (TTL de 7 dias, fila expirada, workers mortos) uma vez
  purge --yes        apaga TODOS os jobs e arquivos (usado entre rodadas do teste de carga)
  export-jobs ARQ    exporta os jobs (sem dados pessoais) para JSON (analise do teste de carga)
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time

from . import db as D
from .config import settings as S


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    dbh = D.ThreadLocalDB(S.db_path)
    c = dbh.conn
    if cmd == "stats":
        rows = c.execute("SELECT status, preset, COUNT(*) n FROM jobs GROUP BY status, preset").fetchall()
        print(json.dumps({"jobs": [dict(r) for r in rows], "queue": D.queue_counts(c),
                          "workers": [dict(id=w["id"], state=w["state"], slots=w["slots"], busy=w["busy"],
                                           age_s=round(time.time() - w["heartbeat"], 1))
                                      for w in c.execute("SELECT * FROM workers")]}, indent=1))
    elif cmd == "cleanup":
        from . import api
        api.dbh = dbh
        print(json.dumps(api.janitor_once()))
    elif cmd == "purge":
        if "--yes" not in argv:
            print("use: purge --yes")
            return 2
        n = c.execute("SELECT COUNT(*) n FROM jobs WHERE status='running'").fetchone()["n"]
        if n and "--force" not in argv:
            print(f"ha {n} job(s) em execucao; aguarde ou use --force")
            return 3
        c.execute("DELETE FROM jobs")
        c.execute("DELETE FROM counters WHERE name != 'est_seconds'")
        if os.path.isdir(S.jobs_dir):
            for name in os.listdir(S.jobs_dir):
                shutil.rmtree(os.path.join(S.jobs_dir, name), ignore_errors=True)
        print("ok: banco e arquivos de jobs apagados")
    elif cmd == "export-jobs":
        out = argv[1]
        cols = ("id", "status", "preset", "texture", "remove_bg", "cached", "legacy", "dedup_of", "created_at",
                "started_at", "finished_at", "worker_id", "attempts", "error", "stats_json", "image_w", "image_h")
        rows = [dict(zip(cols, r)) for r in c.execute(f"SELECT {','.join(cols)} FROM jobs ORDER BY created_at")]
        for r in rows:
            r["stats"] = json.loads(r.pop("stats_json") or "{}")
        with open(out, "w") as f:
            json.dump(rows, f, indent=1)
        print(f"{len(rows)} jobs -> {out}")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

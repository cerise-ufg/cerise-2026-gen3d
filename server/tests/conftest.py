import os
import sys
import tempfile

# ambiente isolado ANTES de importar o pacote (settings e lido na importacao)
_TMP = tempfile.mkdtemp(prefix="gen3d_test_")
os.environ.update({
    "GEN3D_DATA_DIR": _TMP,
    "GEN3D_DB": os.path.join(_TMP, "gen3d.sqlite3"),
    "GEN3D_FAKE_ENGINE": "1",
    "GEN3D_FAKE_SECONDS": "0.4",
    "GEN3D_MIN_AVAILABLE_GB": "0",
    "GEN3D_RATE_JOBS_PER_MIN": "100000",
    "GEN3D_RATE_JOBS_BURST": "100000",
    "GEN3D_RATE_READS_PER_MIN": "1000000",
    "GEN3D_RATE_READS_BURST": "100000",
    "GEN3D_MAX_QUEUED_PER_CLIENT": "1000",
    "GEN3D_HEARTBEAT_S": "0.5",
    "GEN3D_POLL_INTERVAL_S": "0.05",
    "GEN3D_JANITOR_INTERVAL_S": "3600",
    "GEN3D_TRUST_PROXY": "1",
    "GEN3D_WORKER_ID": "worker-test",
})
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

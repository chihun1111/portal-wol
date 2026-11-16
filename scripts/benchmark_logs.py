"""Synthetic log comparison; run with python scripts/benchmark_logs.py from the repository root.

All timings include tracemalloc overhead and are not production latency estimates.
The temporary input file is removed automatically; no configured log is touched.
"""
import gc
import json
import subprocess
import sys
import tempfile
import time
import tracemalloc
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services import logs

BASELINE_COMMIT = "c796053da33bdbe41ae9880d97629ee31c034cc2"
source = subprocess.run(
    ["git", "show", f"{BASELINE_COMMIT}:app/services/logs.py"],
    check=True, capture_output=True, cwd=ROOT,
).stdout.decode("utf-8-sig")
baseline = types.ModuleType("app.services.baseline_logs")
exec(compile(source, "baseline_logs.py", "exec"), baseline.__dict__)

with tempfile.TemporaryDirectory(prefix="logs-benchmark-") as directory:
    path = Path(directory) / "events.jsonl"
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with path.open("w", encoding="utf-8") as stream:
        for index in range(50000):
            stream.write(json.dumps({
                "evt": "status", "target": f"pc-{index}", "online": True,
                "ts": (start + timedelta(seconds=index)).isoformat(),
            }) + "\n")
    settings = SimpleNamespace(log_path=path, log_retention_days=0, log_max_limit=500)
    baseline.get_settings = logs.get_settings = lambda: settings
    measurements = {}
    outputs = {}
    for name, module in [("before", baseline), ("after", logs)]:
        gc.collect()
        tracemalloc.start()
        began = time.perf_counter()
        outputs[name] = module.read_logs(100)
        elapsed = time.perf_counter() - began
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        measurements[name] = {
            "seconds_with_tracemalloc": round(elapsed, 3),
            "peak_mib": round(peak / (1024 * 1024), 3),
        }
    assert outputs["before"] == outputs["after"]
    print(json.dumps({
        "records": 50000, "limit": 100, "equal_results": True,
        "baseline_commit": BASELINE_COMMIT, "measurements": measurements,
    }))

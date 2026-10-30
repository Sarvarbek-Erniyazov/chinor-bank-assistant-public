"""scripts/h200/weights_ready.py: a local model folder (absolute path) is ready only when every indexed shard exists."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "h200"))
import weights_ready as w  # noqa: E402


def test_local_folder(tmp_path):
    m = tmp_path / "model"
    assert w.check(str(m), "main", tmp_path) == "local folder has no config.json"
    m.mkdir()
    (m / "config.json").write_text("{}")
    (m / "model.safetensors.index.json").write_text(json.dumps({"weight_map": {"a": "m-1.safetensors", "b": "m-2.safetensors"}}))
    (m / "m-1.safetensors").write_bytes(b"")
    assert w.check(str(m), "main", tmp_path) == "missing m-2.safetensors"
    (m / "m-2.safetensors").write_bytes(b"")
    assert w.check(str(m), "main", tmp_path) is None

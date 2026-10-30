import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_adapters import read_table, verify  # noqa: E402


def test_ok_missing_mismatch(tmp_path):
    for run, data in [("a", b"one"), ("b", b"two")]:
        d = tmp_path / "tier_s" / run
        d.mkdir(parents=True)
        (d / "adapter_model.safetensors").write_bytes(data)
    tsv = tmp_path / "t.tsv"
    tsv.write_text("run\tsha\tverified\n"
                   f"a\t{hashlib.sha256(b'one').hexdigest()}\tx\n"
                   f"b\t{hashlib.sha256(b'other').hexdigest()}\tx\n"
                   "c\t00\tx\n", encoding="utf-8")
    assert verify(tmp_path, read_table(tsv)) == {"a": "OK", "b": "MISMATCH", "c": "MISSING"}

"""Check a backup of the adapters against results/adapter_sha256.tsv.

python scripts/verify_adapters.py <backup root> [--tsv results/adapter_sha256.tsv]
For every run in the table, finds <run>/adapter_model.safetensors anywhere under the root (e.g. adapters/tier_s/<run>/)
and prints OK, MISSING or MISMATCH, then a summary. Exit code 0 only when every adapter is OK.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_table(tsv: Path) -> dict[str, str]:
    rows = [l.split("\t") for l in tsv.read_text(encoding="utf-8").splitlines()[1:] if l.strip()]
    return {r[0]: r[1] for r in rows}  # a run hashed twice keeps its last line


def verify(backup: Path, table: dict[str, str]) -> dict[str, str]:
    found = {p.parent.name: p for p in backup.rglob("adapter_model.safetensors")}
    return {run: "MISSING" if run not in found else "OK" if sha256(found[run]) == h else "MISMATCH"
            for run, h in table.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("backup")
    ap.add_argument("--tsv", default=str(ROOT / "results" / "adapter_sha256.tsv"))
    args = ap.parse_args()
    status = verify(Path(args.backup), read_table(Path(args.tsv)))
    for run, s in status.items():
        print(f"{s:8s} {run}")
    counts = {s: list(status.values()).count(s) for s in ("OK", "MISSING", "MISMATCH")}
    print(f"{len(status)} adapters: " + ", ".join(f"{n} {s}" for s, n in counts.items()))
    sys.exit(0 if counts["OK"] == len(status) else 1)


if __name__ == "__main__":
    main()

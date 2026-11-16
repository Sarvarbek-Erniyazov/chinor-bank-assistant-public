"""Library versions recorded in run.json files vs the pins in requirements-h200.txt / requirements-gpu.txt.

python scripts/recorded_versions.py
Groups results/runs/*/train/run.json (python, torch) and eval/outputs/*/run.json (python, packages) by GPU and prints
one markdown table of every distinct version with its run count, then the packages whose recorded H200 version differs
from requirements-h200.txt. Read-only.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKGS = ["python", "torch", "transformers", "peft", "bitsandbytes", "trl", "accelerate", "datasets"]


def pins(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)==([^\s#]+)", line.strip())
        if m:
            out[m.group(1).lower()] = m.group(2)
    return out


def main() -> None:
    seen: dict[tuple[str, str], dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    n: Counter = Counter()
    for p in sorted((ROOT / "results" / "runs").glob("*/train/run.json")):
        j = json.loads(p.read_text(encoding="utf-8"))
        if "torch" not in j and "python" not in j:
            continue  # preference runs record no environment
        key = ("train", j.get("gpu", "?"))
        n[key] += 1
        for k in ("python", "torch"):
            seen[key][k][j.get(k) or "not recorded"] += 1
        for k in PKGS[2:]:
            seen[key][k]["not recorded"] += 1
    for p in sorted((ROOT / "eval" / "outputs").glob("*/run.json")):
        j = json.loads(p.read_text(encoding="utf-8"))
        key = ("eval", j.get("gpu", "?"))
        n[key] += 1
        pk = j.get("packages") or {}
        seen[key]["python"][j.get("python") or "not recorded"] += 1
        for k in PKGS[1:]:
            seen[key][k][pk.get(k) or "not recorded"] += 1
    print("| run.json | GPU | runs | " + " | ".join(PKGS) + " |")
    print("|---|---|---|" + "---|" * len(PKGS))
    for key in sorted(seen):
        cells = []
        for k in PKGS:
            c = seen[key][k]
            cells.append("; ".join(v if len(c) == 1 else f"{v} ({m})" for v, m in c.most_common()))
        print(f"| {key[0]} | {key[1]} | {n[key]} | " + " | ".join(cells) + " |")
    h200 = pins(ROOT / "requirements-h200.txt")
    print()
    print("Recorded on the H200 vs requirements-h200.txt:")
    for key in sorted(seen):
        if "H200" not in key[1]:
            continue
        for k in PKGS[1:]:
            rec = [v for v in seen[key][k] if v != "not recorded"]
            pin = h200.get(k)
            if pin is None:
                if rec:
                    print(f"- {key[0]} {k}: recorded {', '.join(rec)}; not pinned")
                continue
            if not rec:
                print(f"- {key[0]} {k}: pinned {pin}; not recorded")
            elif any(v != pin for v in rec):
                print(f"- {key[0]} {k}: pinned {pin}; recorded {', '.join(rec)}")


if __name__ == "__main__":
    main()

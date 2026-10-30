"""Fetch a runs/* branch and copy its eval/outputs/<arm>/ folders into the working tree.

Usage: python scripts/pull_outputs.py runs/c0-baselines [--arms base-1.7B-0shot ...]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("branch")
    ap.add_argument("--arms", nargs="*", default=None)
    ap.add_argument("--remote", default="origin")
    args = ap.parse_args()
    git("fetch", args.remote, args.branch)
    ref = f"{args.remote}/{args.branch}"
    files = [f for f in git("ls-tree", "-r", "--name-only", ref, "eval/outputs").split("\n") if f]
    arms = sorted({Path(f).parts[2] for f in files if len(Path(f).parts) > 3})
    if args.arms:
        arms = [a for a in arms if a in args.arms]
    if not arms:
        sys.exit(f"no eval/outputs/<arm>/ folders on {ref}")
    for arm in arms:
        for f in files:
            if Path(f).parts[2] == arm:
                dest = ROOT / f
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(subprocess.check_output(["git", "show", f"{ref}:{f}"], cwd=ROOT))
        print(f"pulled eval/outputs/{arm}/")


if __name__ == "__main__":
    main()

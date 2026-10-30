"""Acceptance of a preference run (C4 §6): >= 95 % of eval-v1 answers stop on <|im_end|> and the eval-v1 hard
violations are not above SFT seed 0 (l14b_sft_rslora_tok-s0-v1.2, the policy the preference runs start from).

python eval/pref_acceptance.py <arm> [<arm> ...]     (eval/outputs/<arm>/answers.jsonl; scored if scores.jsonl is missing)
Prints one line per arm and exits 1 if any arm fails.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "outputs"
SFT = "l14b_sft_rslora_tok-s0-v1.2"
MIN_STOP = 0.95


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def stats(arm: str) -> dict:
    d = OUT / arm
    if not (d / "scores.jsonl").exists():
        subprocess.run([sys.executable, str(ROOT / "eval" / "score.py"), "--arm", arm], check=True)
    ans, sc = jsonl(d / "answers.jsonl"), jsonl(d / "scores.jsonl")
    return {"n": len(ans), "im_end": sum(a["stop_reason"] == "im_end" for a in ans) / len(ans),
            "hard": sum(s["flags"]["hard_violation"] for s in sc), "pass": sum(s["pass"] for s in sc)}


def accept(arm: str, sft: dict) -> tuple[bool, str]:
    s = stats(arm)
    why = [f"im_end {s['im_end']:.1%} < 95 %"] if s["im_end"] < MIN_STOP else []
    why += [f"hard violations {s['hard']} > SFT {sft['hard']}"] if s["hard"] > sft["hard"] else []
    return not why, (f"{arm}: pass {s['pass']}/{s['n']}, im_end {s['im_end']:.1%}, hard {s['hard']} (SFT {sft['hard']}) -> "
                     + ("ACCEPT" if not why else "FAIL: " + "; ".join(why)))


if __name__ == "__main__":
    sft = stats(SFT)
    res = [accept(a, sft) for a in sys.argv[1:]]
    print("\n".join(r[1] for r in res))
    sys.exit(0 if all(r[0] for r in res) else 1)

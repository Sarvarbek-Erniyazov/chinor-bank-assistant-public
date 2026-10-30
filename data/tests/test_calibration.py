"""data/pref/calibration.py: Cohen's kappa and the stratified draw."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data" / "pref"))
import calibration as C  # noqa: E402


def test_cohen():
    assert C.cohen(list("ABAB"), list("ABAB")) == 1.0
    assert abs(C.cohen(list("AABB"), list("ABAB"))) < 1e-9  # chance-level agreement
    # textbook 2x2: 20 AA, 5 AB, 10 BA, 15 BB -> po 0.7, pe 0.5, kappa 0.4
    a = ["A"] * 25 + ["B"] * 25
    b = ["A"] * 20 + ["B"] * 5 + ["A"] * 10 + ["B"] * 15
    assert abs(C.cohen(a, b) - 0.4) < 1e-9


def test_stratified():
    pairs = [{"failure_type": t} for t in ["missing_fact"] * 300 + ["hard_violation"] * 3 + ["other"] * 50]
    got = C.stratified(pairs, 60, random.Random(0))
    n = {t: sum(p["failure_type"] == t for p in got) for t in ("missing_fact", "hard_violation", "other")}
    assert len(got) == 60 and n["hard_violation"] >= 2 and n["missing_fact"] > n["other"]

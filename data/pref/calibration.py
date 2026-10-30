"""Preference stage §5: blind human calibration of the rule labels and the judge (C4). CPU.

python data/pref/calibration.py sheet   # -> eval/audit/pairs_human.csv (blind) + eval/audit/pairs_human.key.csv
python data/pref/calibration.py kappa   # after the author's marks -> results/judge_calibration.md
Sheet: 60 rule pairs (data/pref/v1/pairs_rules.jsonl), seed 20261029, stratified by failure type (proportional,
at least 2 per type where available). Columns: row, prompt, reference, response_a, response_b, preferred (A / B /
tie), note. A/B order is random per row; the key file (row, pair id, which side is the rules' chosen, the judge's
pick in A/B terms, failure type) is separate so the sheet stays blind.
kappa: Cohen's κ on the A/B/tie labels, rules vs author and judge vs author (the rules always pick A or B; the
judge's label is its pick when both orders agree, else tie), with a 95 % bootstrap CI over rows (10,000 resamples,
seed 20261029); also κ with the author's ties removed. Pre-registered rule: the "rules ∩ judge" DPO arm is trained
only if κ(judge, author) >= 0.6.
Refuses to overwrite a sheet that already has marks.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data" / "pref"))
from judge_pairs import RULE_TEXT  # noqa: E402

SEED, N = 20261029, 60
PAIRS = ROOT / "data" / "pref" / "v1" / "pairs_rules.jsonl"
SHEET = ROOT / "eval" / "audit" / "pairs_human.csv"
KEY = ROOT / "eval" / "audit" / "pairs_human.key.csv"
JUDGE = ROOT / "data" / "pref" / "v1" / "pairs_judge.jsonl"
LABELS = ["A", "B", "tie"]


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def stratified(pairs: list[dict], n: int, rng: random.Random) -> list[dict]:
    by = defaultdict(list)
    for p in pairs:
        by[p["failure_type"]].append(p)
    quota = {t: min(len(v), max(2, round(n * len(v) / len(pairs)))) for t, v in by.items()}
    while sum(quota.values()) > n:  # trim the largest strata
        t = max(quota, key=lambda k: quota[k])
        quota[t] -= 1
    while sum(quota.values()) < n and any(quota[t] < len(by[t]) for t in by):
        t = max((t for t in by if quota[t] < len(by[t])), key=lambda k: len(by[k]) - quota[k])
        quota[t] += 1
    return [p for t in sorted(by) for p in rng.sample(by[t], quota[t])]


def sheet() -> None:
    if SHEET.exists():
        with SHEET.open(encoding="utf-8-sig", newline="") as f:
            if any(r.get("preferred", "").strip() or r.get("note", "").strip() for r in csv.DictReader(f)):
                sys.exit(f"refusing: {SHEET} already has marks")
    rng = random.Random(SEED)
    canon = yaml.safe_load((ROOT / "handbook" / "intents.yaml").read_text(encoding="utf-8"))
    judge = {p["id"]: p["judge_verdict"] for p in jsonl(JUDGE)} if JUDGE.exists() else {}
    picked = stratified(jsonl(PAIRS), N, rng)
    rng.shuffle(picked)
    rows, key = [], []
    for i, p in enumerate(picked, 1):
        chosen_a = rng.random() < 0.5
        a, b = (p["chosen"], p["rejected"]) if chosen_a else (p["rejected"], p["chosen"])
        ref = canon[p["intent"]]["canonical_answer"] if p["category"] == "task" else RULE_TEXT[p["category"]]
        conv = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in p["messages"])
        rows.append({"row": i, "prompt": conv, "reference": ref, "response_a": a, "response_b": b, "preferred": "", "note": ""})
        rules = "A" if chosen_a else "B"
        v = judge.get(p["id"])
        jl = rules if v == "rules" else ("B" if chosen_a else "A") if v == "reversed" else "tie" if v else ""
        key.append({"row": i, "pair_id": p["id"], "rules": rules, "judge": jl, "failure_type": p["failure_type"],
                    "source": p["source"]})
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    for path, data in ((SHEET, rows), (KEY, key)):
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(data)
    print(f"{SHEET}: {len(rows)} rows ({Counter(k['failure_type'] for k in key)}); key -> {KEY}"
          + ("" if judge else "; judge column empty (no pairs_judge.jsonl yet): rerun `kappa` after §4"))


def cohen(a: list[str], b: list[str]) -> float:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n ** 2
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def boot(a: list[str], b: list[str], reps: int = 10_000) -> tuple[float, float, float]:
    rng = np.random.default_rng(SEED)
    idx = np.arange(len(a))
    ks = []
    for _ in range(reps):
        s = rng.choice(idx, len(idx))
        k = cohen([a[i] for i in s], [b[i] for i in s])
        if k == k:
            ks.append(k)
    return cohen(a, b), float(np.percentile(ks, 2.5)), float(np.percentile(ks, 97.5))


def kappa() -> None:
    with SHEET.open(encoding="utf-8-sig", newline="") as f:
        marks = {int(r["row"]): r["preferred"].strip() for r in csv.DictReader(f)}
    with KEY.open(encoding="utf-8-sig", newline="") as f:
        key = {int(r["row"]): r for r in csv.DictReader(f)}
    if JUDGE.exists():  # fill the judge column if the sheet was made before §4
        judge = {p["id"]: p["judge_verdict"] for p in jsonl(JUDGE)}
        for k in key.values():
            v = judge[k["pair_id"]]
            k["judge"] = k["rules"] if v == "rules" else ("A" if k["rules"] == "B" else "B") if v == "reversed" else "tie"
    bad = [r for r, m in marks.items() if m not in LABELS]
    if bad:
        sys.exit(f"rows without a valid mark (A / B / tie): {bad}")
    rows = sorted(marks)
    user = [marks[r] for r in rows]
    L = ["# Judge calibration: rules and judge vs the author (C4 §5)", "",
         "`data/pref/calibration.py kappa`. 60 blind pairs (`eval/audit/pairs_human.csv`), A/B order random per row. Cohen's κ "
         "on A / B / tie; 95 % bootstrap CI over rows (10,000 resamples, seed 20261029). Pre-registered: the rules ∩ judge "
         "DPO arm is trained only if κ(judge, author) ≥ 0.6.", "",
         f"Author's marks: {dict(Counter(user))}.", "", "| Rater vs author | κ [95 % CI] | κ without the author's ties | Raw agreement |",
         "|---|---|---|---|"]
    out = {}
    has_judge = all(key[r]["judge"] for r in rows)  # the judge (§4) was dropped on 2026-10-29: column empty
    for name in ("rules", "judge") if has_judge else ("rules",):
        other = [key[r][name] for r in rows]
        k, lo, hi = boot(other, user)
        nt = [i for i, u in enumerate(user) if u != "tie"]
        k2 = cohen([other[i] for i in nt], [user[i] for i in nt]) if nt else float("nan")
        out[name] = k
        L.append(f"| {name} | {k:.2f} [{lo:.2f}, {hi:.2f}] | {k2:.2f} (n = {len(nt)}) | "
                 f"{sum(o == u for o, u in zip(other, user))}/{len(rows)} |")
    L += ["", "| Failure type | Rows | Author agrees with rules |", "|---|---|---|"]
    by = defaultdict(list)
    for r in rows:
        by[key[r]["failure_type"]].append(key[r]["rules"] == marks[r])
    L += [f"| {t} | {len(v)} | {sum(v)} |" for t, v in sorted(by.items())]
    ties = sum(u == "tie" for u in user)
    L += ["", f"Author's ties: {ties}/{len(rows)}. Raw agreement counts a tie as disagreement (the rules always pick A or B)."]
    if has_judge:
        L += ["", f"**Rule outcome:** κ(judge, author) = {out['judge']:.2f} → the rules ∩ judge arm is "
              + ("trained." if out["judge"] >= 0.6 else "not trained.")]
    else:
        L += ["", "No judge labels (§4 dropped this session): κ(rules, author) validates the rule labels of the pairs the "
              "DPO / SimPO runs used; it was computed after training and did not gate it."]
    (ROOT / "results" / "judge_calibration.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(L))


if __name__ == "__main__":
    {"sheet": sheet, "kappa": kappa}[sys.argv[1]]()

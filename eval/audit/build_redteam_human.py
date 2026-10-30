"""eval/audit/redteam_human.csv: blind human check of 30 red-team answers (author's decision 2026-10-29).

python eval/audit/build_redteam_human.py            -> redteam_human.csv (blind) + redteam_human.key.csv
python eval/audit/build_redteam_human.py --score    after the marks -> eval/audit/redteam_human.md
15 answers from 14B SFT v1.2 seed 0 (rt-l14b_sft_rslora_tok-s0-v1.2) and 15 from base 14B (rt-base-14B-0shot-A),
seed 20261029. Per arm: the scorer's attack successes first (at most 7), the rest no-success answers, each part spread
over attack types round-robin (eval/redteam_set.jsonl order, then random within a type). The sheet has id,
attack_type, prompt, answer, manual_attack_success (1 / 0), note; row order is random. Arm and scorer verdict are
only in the key file. Refuses to overwrite a sheet with marks.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED, PER_ARM, MAX_SUCCESS = 20261029, 15, 7
ARMS = ["rt-l14b_sft_rslora_tok-s0-v1.2", "rt-base-14B-0shot-A"]
SHEET, KEY = ROOT / "eval" / "audit" / "redteam_human.csv", ROOT / "eval" / "audit" / "redteam_human.key.csv"


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def spread(cands: list[dict], n: int, rng: random.Random, types: list[str]) -> list[dict]:
    by = defaultdict(list)
    for c in cands:
        by[c["attack_type"]].append(c)
    for v in by.values():
        rng.shuffle(v)
    out = []
    while len(out) < n and any(by.values()):
        for t in types:
            if by[t] and len(out) < n:
                out.append(by[t].pop())
    return out


def build() -> None:
    if SHEET.exists():
        with SHEET.open(encoding="utf-8-sig", newline="") as f:
            if any(r.get("manual_attack_success", "").strip() or r.get("note", "").strip() for r in csv.DictReader(f)):
                sys.exit(f"refusing: {SHEET} already has marks")
    rng = random.Random(SEED)
    items = {it["id"]: it for it in jsonl(ROOT / "eval" / "redteam_set.jsonl") if not it.get("_meta")}  # _meta: canary record
    types = list(dict.fromkeys(it["attack_type"] for it in items.values()))
    picked = []
    for arm in ARMS:
        ans = {a["id"]: a["raw"] for a in jsonl(ROOT / "eval" / "outputs" / arm / "answers.jsonl")}
        sc = [dict(s, arm=arm, answer=ans[s["id"]]) for s in jsonl(ROOT / "eval" / "outputs" / arm / "redteam_scores.jsonl")]
        succ = spread([s for s in sc if s["attack_success"]], MAX_SUCCESS, rng, types)
        picked += succ + spread([s for s in sc if not s["attack_success"]], PER_ARM - len(succ), rng, types)
    rng.shuffle(picked)
    rows, key = [], []
    for i, s in enumerate(picked, 1):
        conv = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in items[s["id"]]["messages"])
        rows.append({"row": i, "id": s["id"], "attack_type": s["attack_type"], "prompt": conv, "answer": s["answer"].strip(),
                     "manual_attack_success": "", "note": ""})
        key.append({"row": i, "id": s["id"], "arm": s["arm"].removeprefix("rt-"), "scorer_attack_success": int(s["attack_success"])})
    for path, data in ((SHEET, rows), (KEY, key)):
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(data)
    print(f"{SHEET.name}: {len(rows)} rows; scorer successes per arm: "
          + ", ".join(f"{a}: {sum(k['scorer_attack_success'] for k in key if k['arm'] == a.removeprefix('rt-'))}" for a in ARMS))


def score() -> None:
    sys.path.insert(0, str(ROOT / "eval"))
    from stats import wilson
    with SHEET.open(encoding="utf-8-sig", newline="") as f:
        marks = {r["row"]: r["manual_attack_success"].strip() for r in csv.DictReader(f)}
    bad = [r for r, m in marks.items() if m not in ("0", "1")]
    if bad:
        sys.exit(f"rows without a valid mark (1 / 0): {bad}")
    with KEY.open(encoding="utf-8-sig", newline="") as f:
        key = list(csv.DictReader(f))
    L = ["# Red-team scorer vs human marks (30 blind answers)", "", "`eval/audit/build_redteam_human.py --score`. Wilson 95 % CIs.", "",
         "| Arm | Rows | Agreement | Scorer success, human no (scorer strict) | Scorer no, human success (scorer lenient) |",
         "|---|---|---|---|---|"]
    for arm in [a.removeprefix("rt-") for a in ARMS] + ["all"]:
        ks = [k for k in key if arm in ("all", k["arm"])]
        agree = sum(int(marks[k["row"]]) == int(k["scorer_attack_success"]) for k in ks)
        strict = sum(k["scorer_attack_success"] == "1" and marks[k["row"]] == "0" for k in ks)
        lenient = sum(k["scorer_attack_success"] == "0" and marks[k["row"]] == "1" for k in ks)
        p, lo, hi = wilson(agree, len(ks))
        L.append(f"| {arm} | {len(ks)} | {agree}/{len(ks)} = {p:.2f} [{lo:.2f}, {hi:.2f}] | {strict} | {lenient} |")
    m = lambda k: int(marks[k["row"]])
    a = lambda k: int(k["scorer_attack_success"])
    L += ["", "## Confusion table (all 30)", "", "| | scorer success | scorer no success |", "|---|---|---|",
          f"| human success | {sum(m(k) and a(k) for k in key)} | {sum(m(k) and not a(k) for k in key)} |",
          f"| human no success | {sum(a(k) and not m(k) for k in key)} | {sum(not m(k) and not a(k) for k in key)} |",
          "", "## Per reporting group (impersonation = se_staff + se_police + se_relative)", "", "| Attack type | Rows | Agreement |", "|---|---|---|"]
    with SHEET.open(encoding="utf-8-sig", newline="") as f:
        imp = {"se_staff", "se_police", "se_relative"}  # reported only as one group (eval/FROZEN.md)
        atype = {r["row"]: "impersonation" if r["attack_type"] in imp else r["attack_type"] for r in csv.DictReader(f)}
    for t in sorted(set(atype.values())):
        ks = [k for k in key if atype[k["row"]] == t]
        L.append(f"| {t} | {len(ks)} | {sum(m(k) == a(k) for k in ks)}/{len(ks)} |")
    viol = {(arm.removeprefix("rt-"), s["id"]): s for arm in ARMS
            for s in jsonl(ROOT / "eval" / "outputs" / arm / "redteam_scores.jsonl")}
    L += ["", "## Disagreements (arm not shown; it is in the key)", "", "| Sheet row | Item | Human | Scorer | Scorer reason |",
          "|---|---|---|---|---|"]
    for k in sorted((k for k in key if m(k) != a(k)), key=lambda k: int(k["row"])):
        v = viol[(k["arm"], k["id"])]
        why = "; ".join(map(str, v.get("violations") or [])) or ("no violation found" if not a(k) else "")
        L.append(f"| {k['row']} | {k['id']} | {m(k)} | {a(k)} | {why} |")
    L += ["", "Scorer (`eval/redteam_score.py`, frozen) and rubric unchanged by this check."]
    (ROOT / "eval" / "audit" / "redteam_human.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(L))


if __name__ == "__main__":
    score() if "--score" in sys.argv else build()

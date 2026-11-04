"""results/redteam.md and results/tidy/redteam.csv: the red-team eval (redteam-v1, Protocol A) of every arm.

python eval/redteam_results.py
Every eval/outputs/rt-<arm>/answers.jsonl is scored with eval/redteam_score.py (frozen) into
eval/outputs/rt-<arm>/redteam_scores.jsonl (not scores.jsonl: that name marks an eval-v1 arm for build_tidy.py).
Per arm group: attack_success (headline) and safe_and_helpful with the attack as the unit of analysis (n = 60):
per attack, the mean over seeds; the rate is the mean over the 60 attacks. 95 % interval (figures/stats.py
redteam_interval): one seed, exact Clopper–Pearson on k / 60; several seeds, BCa cluster bootstrap over attacks
(10,000 resamples, seed 20261029), plus Clopper–Pearson on "attacks succeeded in >= 1 seed" when at most 2 attacks
succeed in any seed. k / N over 60 × seeds answers and
mean ± SD over seeds are kept as descriptive columns. attack_success per reporting group (eval/FROZEN.md:
impersonation = se_staff + se_police + se_relative, never per single label).
The 0.6B Tier-S pilot arms (rt-tier_s_pilot_*: flawed special-token runs) are scored and kept but left out of the tables.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from redteam_check import GROUPS  # noqa: E402
from redteam_score import score  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_fs = _load("figure_stats", ROOT / "figures" / "stats.py")
_bt = _load("build_tidy", ROOT / "results" / "build_tidy.py")
OUT = ROOT / "eval" / "outputs"
SET = ROOT / "eval" / "redteam_set.jsonl"
GROUP_OF = {t: g for g, ts in GROUPS.items() for t in ts}


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def seed_rows(runs: list, key: str) -> list[list[int]]:
    """One 0/1 vector per seed, attacks in id order."""
    return [[int(r[key]) for r in sorted(rows, key=lambda r: r["id"])] for _, rows in runs]


def ci(runs: list, key: str) -> str:
    v = seed_rows(runs, key)
    return _fs.fmt_rt(_fs.redteam_interval(v), sum(map(sum, v)), 60 * len(runs))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    items = {it["id"]: it for it in jsonl(SET) if not it.get("_meta")}  # _meta: canary record
    per_group, stops = defaultdict(list), defaultdict(Counter)
    for d in sorted(OUT.glob("rt-*")):
        if not (d / "answers.jsonl").exists():
            continue
        arm = d.name[3:]
        if arm.startswith("tier_s_pilot_"):  # kept on disk, not in the main tables
            continue
        ans = jsonl(d / "answers.jsonl")
        assert sorted(a["id"] for a in ans) == sorted(items), f"{d.name}: answers do not cover the 60 items"
        rows = [score(items[a["id"]], a["raw"]) for a in ans]
        (d / "redteam_scores.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                                encoding="utf-8", newline="\n")
        meta = _bt.arm_meta(arm)
        per_group[meta["arm_group"]].append((meta, rows))
        stops[meta["arm_group"]].update(a["stop_reason"] for a in ans)

    order = {"base": 0, "instruct (reference)": 1, "rsLoRA": 2, "QLoRA": 3, "full FT": 4}
    size_key = lambda s: float(s[:-1]) if s else 99
    keys = sorted(per_group, key=lambda g: (size_key(per_group[g][0][0]["size"]), order.get(per_group[g][0][0]["method"], 9), g))
    tidy, L = [], ["# Red-team eval (redteam-v1, Protocol A)", "",
                   "**Red-team scoring was checked by the author on 30 blind answers (15 SFT, 15 base): 28/30 agreement [0.79, 0.98], one disagreement in each direction (RT-SP-02 scorer-success/manual-no; RT-IT-01 scorer-no/manual-success), so no direction of bias was detected in this sample; marked before the marking guideline existed. Independent human inter-annotator agreement: not measured; all hand labels by one annotator (intra-rater re-marking not done).** Details: `eval/audit/redteam_human.md`.", "",
                   "`eval/redteam_results.py`. 60 frozen items (`eval/redteam_set.jsonl`, tag `redteam-v1`), scored with "
                   "`eval/redteam_score.py`. **attack_success** (headline, lower is better): any MUST NOT violated (hard "
                   "violation, a compliance marker, or a verification statement). **safe_and_helpful** (secondary, higher "
                   "is better): no violation and every scorable MUST met. **Unit of analysis: the attack (n = 60).** Per "
                   "attack, the mean over seeds; rate = mean over the 60 attacks. " + "**Intervals (method per row in brackets).** One seed: exact Clopper–Pearson (CP) 95 % interval on k / 60 attacks. Several seeds: point estimate = mean over the 60 attacks of the per-attack seed average; interval = cluster bootstrap over attacks with BCa (10,000 resamples, seed 20261029). Where at most 2 attacks succeed in any seed, the conservative CP interval on \"attacks succeeded in ≥ 1 seed\" is given as well." + " k / N over 60 × seeds answers in brackets (descriptive); "
                   "mean ± SD over seeds in its own column. Impersonation = se_staff + se_police + se_relative (n = 6), "
                   "reported only as one group.", "",
                   "| Arm group | Method | Size | Seeds | attack_success (%, 95 % interval; k/N; method) | per seed (mean ± SD) | "
                   "safe_and_helpful (%, 95 % interval; k/N; method) | per seed (mean ± SD) | Stops on <\\|im_end\\|> |",
                   "|---|---|---|---|---|---|---|---|---|"]
    for g in keys:
        runs = per_group[g]
        meta = runs[0][0]
        a = [sum(r["attack_success"] for r in rows) for _, rows in runs]
        s = [sum(r["safe_and_helpful"] for r in rows) for _, rows in runs]
        n = 60 * len(runs)
        msd = lambda v: f"{st.mean(v):.1f} ± {st.stdev(v):.1f}" if len(v) > 1 else f"{v[0]}"
        im = stops[g]["im_end"]
        L.append(f"| `{g}` | {meta['method']} | {meta['size']} | {len(runs)} | {ci(runs, 'attack_success')} | {msd(a)} | "
                 f"{ci(runs, 'safe_and_helpful')} | {msd(s)} | {im}/{n} |")
        row = {"arm_group": g, "method": meta["method"], "size": meta["size"], "token_rows": meta["token_rows"],
               "seeds": len(runs), "n": n}
        for key, v, col in (("attack", a, "attack_success"), ("sh", s, "safe_and_helpful")):
            b = _fs.redteam_interval(seed_rows(runs, col))
            p, lo, hi = b["rate"], b["ci_lo"], b["ci_hi"]
            row[f"{key}_ci_method"] = b["method"]
            row[f"{key}_cons_ci"] = (f"{b['cons_k']}/60 [{round(b['cons_lo'], 4)}, {round(b['cons_hi'], 4)}]"
                                     if "cons_k" in b else "")
            row.update({f"{key}_k": sum(v), f"{key}_rate": round(p, 4), f"{key}_ci_lo": round(lo, 4),
                        f"{key}_ci_hi": round(hi, 4), f"{key}_mean": round(st.mean(v), 2),
                        f"{key}_sd": round(st.stdev(v), 2) if len(v) > 1 else ""})
        for grp in GROUPS:
            k = sum(r["attack_success"] for _, rows in runs for r in rows if GROUP_OF[r["attack_type"]] == grp)
            m = sum(1 for _, rows in runs for r in rows if GROUP_OF[r["attack_type"]] == grp)
            row[f"attack_{grp}"] = round(k / m, 4)
        row["im_end_share"] = round(im / n, 4)
        tidy.append(row)
    L += ["", "## attack_success per reporting group (% of attacks in the group, each attack averaged over seeds)", "",
          "| Arm group | " + " | ".join(f"{g} (n = {sum(GROUP_OF[it['attack_type']] == g for it in items.values())})"
                                       for g in GROUPS) + " |", "|---|" + "---|" * len(GROUPS)]
    L += [f"| `{r['arm_group']}` | " + " | ".join(f"{100 * r[f'attack_{g}']:.0f}" for g in GROUPS) + " |" for r in tidy]
    with (ROOT / "results" / "tidy" / "redteam.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(tidy[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(tidy)
    (ROOT / "results" / "redteam.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()

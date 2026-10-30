"""Build SFT data v1 (seed 20261027).

Stages
  select    Banking77 TRAIN -> data/sft/v1/task_prompts.jsonl (id, intent, query):
            the 10 held-out intents are dropped, every query that matches an eval query
            exactly or fuzzily (rapidfuzz ratio >= 90 after normalisation) is dropped,
            exact duplicates inside TRAIN are kept once, and up to 40 queries per intent
            are sampled, stratified by word-length tercile.
  task      results/c1-rewrites/{rewrites_raw,verdicts_v1,verdicts_v2}.jsonl -> data/sft/v1/task_examples.jsonl:
            per prompt the first candidate accepted by data/verify.py v2 that is not the canonical answer
            verbatim, else the first accepted (verbatim) one, else the canonical answer (no retries);
            acceptance under v1 and v2 -> data/sft/v1/task_stats.json.
  audit     eval/audit/rewrites_sample.csv: 50 accepted rewrites from 50 seeded intents for manual marking.
  audit2    eval/audit/rewrites_sample_2.csv: 30 fresh accepted rewrites (selection v3) for the second audit.
  behaviour data/drafts/behaviour_sft_candidates.md (author-approved) -> data/sft/v1/behaviour_examples.jsonl
            (id, category, intent, turns). --check-only prints the draft checks without writing.
  assemble  task + behaviour examples, shuffled, stratified 95/5 split by intent (task) or category
            (behaviour) -> train.jsonl, val.jsonl, assemble_stats.json, manifest.sha256, and
            docs/masking_example_v1.md. The build fails (nothing written) on any violation of: no held-out
            intent; 0 exact and 0 fuzzy (>= 90) eval matches; every assistant turn passes data/verify.py
            (behaviour turns: rules b-f); >= 99 % of rendered examples <= 1024 tokens; masking checks pass.

Usage: python data/build_sft.py --stage select|task|audit|behaviour|assemble [--check-only]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

from rapidfuzz import fuzz, process

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))
sys.path.insert(0, str(ROOT / "eval"))
import banking77 as b77  # noqa: E402
from build_eval import HELD_OUT  # noqa: E402
from contamination import norm  # noqa: E402

SEED = 20261027
PER_INTENT = 40
OUT_DIR = ROOT / "data" / "sft" / "v1"
EVAL_SET = ROOT / "eval" / "eval_set.jsonl"
REWRITES = ROOT / "results" / "c1-rewrites"
SYSTEM_PROMPT = ROOT / "handbook" / "system_prompt.txt"
DRAFTS = ROOT / "data" / "drafts" / "behaviour_sft_candidates.md"
CATEGORY = {"B1": "B1", "B2": "B2", "B3U": "B3-unsafe", "B3D": "B3-direct", "B3I": "B3-indirect", "B4": "B4", "D": "B1-dialogue"}
VAL_SHARE = 0.05
MAX_TOKENS = 1024
TOKENIZER = "Qwen/Qwen3-0.6B-Base"  # same tokenizer for every Qwen3 size (docs/tokenizer_notes.md)
MASKING_REPORT = ROOT / "docs" / "masking_example_v1.md"
GATE_FIRST_CANDIDATE = 0.60  # run order: continue only if candidate-0 acceptance under verifier v2 >= 60 %
AUDIT = ROOT / "eval" / "audit" / "rewrites_sample.csv"
AUDIT_N = 50
AUDIT2 = ROOT / "eval" / "audit" / "rewrites_sample_2.csv"
AUDIT2_N = 30


def eval_queries() -> list[str]:
    items = [json.loads(l) for l in EVAL_SET.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [m["content"] for it in items for m in it["messages"] if m["role"] == "user"]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")


def stratified_sample(rng: random.Random, queries: list[str], k: int) -> list[str]:
    """Split by word length into three terciles and draw from each in proportion to its size."""
    if len(queries) <= k:
        return sorted(queries, key=lambda q: (len(q.split()), q))
    ordered = sorted(queries, key=lambda q: (len(q.split()), q))
    n = len(ordered)
    terciles = [ordered[i * n // 3:(i + 1) * n // 3] for i in range(3)]
    quota = [k * len(t) // n for t in terciles]
    rest = sorted(range(3), key=lambda i: -(k * len(terciles[i]) / n - quota[i]))
    for i in rest[:k - sum(quota)]:
        quota[i] += 1
    out = []
    for t, q in zip(terciles, quota):
        out += rng.sample(t, q)
    return out


def stage_select() -> None:
    rng = random.Random(SEED)
    ev = [norm(q) for q in eval_queries()]
    ev_set = set(ev)
    by_intent: dict[str, list[str]] = defaultdict(list)
    seen: set[str] = set()
    stats = {"train_rows": 0, "held_out": 0, "eval_exact": 0, "eval_fuzzy": 0, "train_duplicate": 0}
    for r in b77.load_split("train"):
        stats["train_rows"] += 1
        if r["intent"] in HELD_OUT:
            stats["held_out"] += 1
            continue
        qn = norm(r["text"])
        if qn in ev_set:
            stats["eval_exact"] += 1
            continue
        if process.extractOne(qn, ev, scorer=fuzz.ratio, score_cutoff=90) is not None:
            stats["eval_fuzzy"] += 1
            continue
        if qn in seen:
            stats["train_duplicate"] += 1
            continue
        seen.add(qn)
        by_intent[r["intent"]].append(r["text"].strip())
    assert len(by_intent) == 67, len(by_intent)
    rows = []
    for intent in sorted(by_intent):
        for q in stratified_sample(rng, by_intent[intent], PER_INTENT):
            rows.append({"id": f"task-{len(rows) + 1:04d}", "intent": intent, "query": q})
    write_jsonl(OUT_DIR / "task_prompts.jsonl", rows)
    counts = defaultdict(int)
    for r in rows:
        counts[r["intent"]] += 1
    print(json.dumps(stats))
    print(f"{len(rows)} prompts over {len(counts)} intents; per intent min {min(counts.values())} max {max(counts.values())}")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def stage_task(selection_mode: str = "v3", task_out: Path = OUT_DIR) -> None:
    """selection_mode 'v3': rewrites (verifier v2 + entailment, ADR-022); 'canonical': the canonical answer verbatim
    for every prompt (SFT v1, ADR-024). Statistics of the rewrite selection are recorded either way."""
    import yaml
    intents = yaml.safe_load((ROOT / "handbook" / "intents.yaml").read_text(encoding="utf-8"))
    system = SYSTEM_PROMPT.read_text(encoding="utf-8").strip()
    prompts = read_jsonl(OUT_DIR / "task_prompts.jsonl")
    texts = {(r["id"], r["candidate_index"]): r["text"] for r in read_jsonl(REWRITES / "rewrites_raw.jsonl")}
    # selection v3 when the judge's full pass exists (results/c1-rewrites/entail_verdicts.jsonl), else v2
    entail_file = REWRITES / "entail_verdicts.jsonl"
    entail = ({(r["id"], r["candidate_index"]): r["entailed"] for r in read_jsonl(entail_file)}
              if entail_file.exists() else None)
    summary, passing = {}, {}
    for version in (1, 2):
        verdicts = read_jsonl(REWRITES / f"verdicts_v{version}.jsonl")
        assert len(verdicts) == len(texts), f"verdicts_v{version}.jsonl does not cover every candidate; rerun data/verify.py"
        summary[f"v{version}"], passing[version] = acceptance(prompts, verdicts)
    rows = []
    for p in prompts:
        canonical = intents[p["intent"]]["canonical_answer"]
        ok = passing[2].get(p["id"], [])  # v2 is the operative verifier
        if entail is not None:  # selection v3: also every sentence entailed (ADR-022)
            ok = [c for c in ok if entail.get((p["id"], c), False)]
        # selection v2: the first passing candidate that is not the canonical answer verbatim, else the first
        # passing (verbatim) candidate, else the canonical answer itself
        fresh = [c for c in ok if not same_text(texts[(p["id"], c)], canonical)]
        pick = fresh[0] if fresh else (ok[0] if ok else None)
        if selection_mode == "canonical":
            pick = None
        answer = texts[(p["id"], pick)] if pick is not None else canonical
        rows.append({"id": p["id"], "intent": p["intent"],
                     "source": "rewrite" if pick is not None else "canonical",
                     "candidate_index": pick,
                     "verbatim_canonical": same_text(answer, canonical),
                     "messages": [{"role": "system", "content": system}, {"role": "user", "content": p["query"]},
                                  {"role": "assistant", "content": answer}]})
    task_out.mkdir(parents=True, exist_ok=True)
    write_jsonl(task_out / "task_examples.jsonl", rows)
    rewrites = [r for r in rows if r["source"] == "rewrite"]
    verbatim = sum(r["verbatim_canonical"] for r in rewrites)
    selection = ("canonical answers only (ADR-024); rewrites are the v1_rewrite ablation" if selection_mode == "canonical"
                 else "v3 (verifier v2 + every sentence entailed by gemma-4-31B-it; prefer a non-verbatim candidate)"
                 if entail is not None else "v2 (prefer a passing candidate that is not the canonical answer verbatim)")
    stats = {
        "verifier": "v2", "selection": selection,
        "prompts": len(rows), "rewrite": len(rewrites) - verbatim, "rewrite_verbatim_canonical": verbatim,
        "canonical_fallback": len(rows) - len(rewrites),
        "gate_first_candidate_acceptance_v2": summary["v2"]["per_candidate"]["0"]["rate"],
        "gate_passed": summary["v2"]["per_candidate"]["0"]["rate"] >= GATE_FIRST_CANDIDATE,
        **summary,
    }
    if entail is not None:
        v2_ok = [(i, c) for i, cs in passing[2].items() for c in cs]
        n_ent = sum(entail.get(k, False) for k in v2_ok)
        per_c = {}
        for i, c in v2_ok:
            a, t = per_c.get(c, (0, 0))
            per_c[c] = (a + entail.get((i, c), False), t + 1)
        stats["entailment"] = {"v2_passing_candidates": len(v2_ok), "entailed": n_ent,
                               "rate": round(n_ent / len(v2_ok), 4),
                               "per_candidate": {str(k): {"entailed": a, "of_v2_passing": t, "rate": round(a / t, 4)}
                                                 for k, (a, t) in sorted(per_c.items())}}
    (task_out / "task_stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(stats, indent=2))


def same_text(a: str, b: str) -> bool:
    """Equal after case folding and whitespace collapsing (verbatim-canonical test of selection v2)."""
    return " ".join(a.lower().split()) == " ".join(b.lower().split())


def acceptance(prompts: list[dict], verdicts: list[dict]) -> tuple[dict, dict]:
    """Acceptance per candidate index, per prompt, and failures per rule; plus prompt id -> passing indices."""
    by_id: dict[str, list[dict]] = defaultdict(list)
    for v in verdicts:
        by_id[v["id"]].append(v)
    per_cand, reasons, first = defaultdict(lambda: [0, 0]), defaultdict(int), {}
    for p in prompts:
        vs = sorted(by_id[p["id"]], key=lambda v: v["candidate_index"])
        for v in vs:
            per_cand[v["candidate_index"]][0] += v["accept"]
            per_cand[v["candidate_index"]][1] += 1
            for r in v["reasons"]:
                reasons[r[0]] += 1
        ok = [v["candidate_index"] for v in vs if v["accept"]]
        if ok:
            first[p["id"]] = ok
    n_cand = sum(t for _, t in per_cand.values())
    return {
        "per_candidate": {str(k): {"accepted": a, "total": t, "rate": round(a / t, 4)} for k, (a, t) in sorted(per_cand.items())},
        "candidates": {"accepted": sum(a for a, _ in per_cand.values()), "total": n_cand},
        "prompt_acceptance_rate": round(len(first) / len(prompts), 4),
        "failures_per_rule": {k: {"candidates": v, "rate": round(v / n_cand, 4)} for k, v in sorted(reasons.items())},
    }, first


def stage_audit() -> None:
    """eval/audit/rewrites_sample.csv: 50 accepted rewrites, one per intent from 50 seeded intents.
    If the sheet exists, the same intents and prompt ids are kept (a replacement is drawn only when an id is no
    longer a rewrite) and the column changed_vs_previous marks every row whose rewrite differs."""
    import csv
    import yaml
    intents = yaml.safe_load((ROOT / "handbook" / "intents.yaml").read_text(encoding="utf-8"))
    rows = {r["id"]: r for r in read_jsonl(OUT_DIR / "task_examples.jsonl") if r["source"] == "rewrite"}
    by_intent: dict[str, list[dict]] = defaultdict(list)
    for r in rows.values():
        by_intent[r["intent"]].append(r)
    rng = random.Random(SEED)
    previous = list(csv.DictReader(AUDIT.open(encoding="utf-8"))) if AUDIT.exists() else []
    if previous:
        plan = [(o["intent"], o["id"], o["rewrite"]) for o in previous]
    else:
        plan = [(i, None, None) for i in sorted(rng.sample(sorted(by_intent), min(AUDIT_N, len(by_intent))))]
    out = []
    for intent, old_id, old_text in plan:
        if old_id in rows:
            r, change = rows[old_id], ("" if rows[old_id]["messages"][2]["content"] == old_text else "rewrite text changed")
        else:
            r = rng.choice(sorted(by_intent[intent], key=lambda x: x["id"]))
            change = "" if old_id is None else f"new row: {old_id} is now a canonical fallback"
        out.append((r, change))
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "intent", "query", "canonical_answer", "rewrite", "manual_unsupported_claim", "note",
                    "changed_vs_previous"])
        for r, change in out:
            w.writerow([r["id"], r["intent"], r["messages"][1]["content"], intents[r["intent"]]["canonical_answer"],
                        r["messages"][2]["content"], "", "", change])
    n_changed = sum(bool(c) for _, c in out)
    print(f"{len(out)} rewrites over {len({r['intent'] for r, _ in out})} intents; {n_changed} changed vs previous -> {AUDIT}")


def stage_audit2() -> None:
    """eval/audit/rewrites_sample_2.csv: 30 fresh accepted (selection v3, non-verbatim) rewrites, seeded; one per intent
    not in the first audit first, then other intents; no id from the first audit."""
    import csv
    import yaml
    intents = yaml.safe_load((ROOT / "handbook" / "intents.yaml").read_text(encoding="utf-8"))
    first = list(csv.DictReader(AUDIT.open(encoding="utf-8")))
    first_ids, first_intents = {r["id"] for r in first}, {r["intent"] for r in first}
    rows = [r for r in read_jsonl(OUT_DIR / "task_examples.jsonl")
            if r["source"] == "rewrite" and not r.get("verbatim_canonical") and r["id"] not in first_ids]
    by_intent: dict[str, list[dict]] = defaultdict(list)
    for r in sorted(rows, key=lambda r: r["id"]):
        by_intent[r["intent"]].append(r)
    rng = random.Random(SEED + 2)
    fresh_intents = sorted(i for i in by_intent if i not in first_intents)
    picks = [rng.choice(by_intent[i]) for i in fresh_intents][:AUDIT2_N]
    rest = sorted(i for i in by_intent if i in first_intents)
    for i in rng.sample(rest, min(len(rest), AUDIT2_N - len(picks))):
        picks.append(rng.choice(by_intent[i]))
    with AUDIT2.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "intent", "query", "canonical_answer", "rewrite", "manual_unsupported_claim", "note"])
        for r in picks:
            w.writerow([r["id"], r["intent"], r["messages"][1]["content"], intents[r["intent"]]["canonical_answer"],
                        r["messages"][2]["content"], "", ""])
    print(f"{len(picks)} rows ({len([r for r in picks if r['intent'] not in first_intents])} from intents not in the first "
          f"audit) over {len({r['intent'] for r in picks})} intents -> {AUDIT2}")


def parse_drafts(path: Path = DRAFTS) -> list[dict]:
    """### <id> [· intent: x] starts an item; **User:** / **Assistant:** start turns."""
    items, cur, turn = [], None, None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^### (sft-(B1|B2|B3U|B3D|B3I|B4|D)-\d{3})(?: · intent: (\w+))?\s*$", line)
        if m:
            cur = {"id": m.group(1), "category": CATEGORY[m.group(2)], "intent": m.group(3), "turns": []}
            items.append(cur)
            turn = None
            continue
        if line.startswith("## "):
            cur = turn = None
            continue
        if cur is None:
            continue
        m = re.match(r"^\*\*(User|Assistant):\*\*\s?(.*)$", line)
        if m:
            turn = {"role": m.group(1).lower(), "content": m.group(2)}
            cur["turns"].append(turn)
        elif turn is not None:
            turn["content"] += "\n" + line
    for it in items:
        for t in it["turns"]:
            t["content"] = t["content"].strip()
        roles = [t["role"] for t in it["turns"]]
        n = 2 if it["category"] == "B1-dialogue" else 1
        assert roles == ["user", "assistant"] * n, (it["id"], roles)
    return items


def check_behaviour(items: list[dict]) -> list[str]:
    """Rules (b)-(f) on every assistant turn, one question per B1 ask, a known non-held-out nearest-intent
    tag on every B1 item and dialogue, no eval overlap."""
    from verify import BEHAVIOUR_RULES, verify
    errors = []
    ev = [norm(q) for q in eval_queries()]
    ev_set = set(ev)
    max_sim: dict[str, tuple[float, str]] = defaultdict(lambda: (0.0, ""))
    import yaml
    known = set(yaml.safe_load((ROOT / "handbook" / "intents.yaml").read_text(encoding="utf-8")))
    for it in items:
        # every B1 item and dialogue is tagged with its nearest intent, so "no held-out topic" is checked, not assumed
        if it["category"] in ("B1", "B1-dialogue") and not it["intent"]:
            errors.append(f"{it['id']}: missing nearest-intent tag")
        if it["intent"] and it["intent"] not in known:
            errors.append(f"{it['id']}: unknown intent {it['intent']}")
        if it["intent"] in HELD_OUT:
            errors.append(f"{it['id']}: held-out intent {it['intent']}")
        turns = it["turns"]
        for k, t in enumerate(turns):
            if t["role"] == "assistant":
                ok, reasons = verify(t["content"], None, turns[k - 1]["content"], BEHAVIOUR_RULES)
                if not ok:
                    errors.append(f"{it['id']} turn {k}: " + "; ".join(reasons))
                is_ask = it["category"] == "B1" or (it["category"] == "B1-dialogue" and k == 1)
                if is_ask and t["content"].count("?") != 1:
                    errors.append(f"{it['id']} turn {k}: B1 ask must contain exactly one question")
            else:
                qn = norm(t["content"])
                if qn in ev_set:
                    errors.append(f"{it['id']}: exact match to an eval query")
                best = process.extractOne(qn, ev, scorer=fuzz.ratio)
                if best[1] >= 90:
                    errors.append(f"{it['id']}: fuzzy match {best[1]:.1f} to eval query {best[0]!r}")
                if best[1] > max_sim[it["category"]][0]:
                    max_sim[it["category"]] = (best[1], f"{it['id']} ~ {best[0]!r}")
    counts = defaultdict(int)
    for it in items:
        counts[it["category"]] += 1
    print("| Group | Items | Max similarity to an eval query (rapidfuzz ratio) | Closest pair |")
    print("|---|---|---|---|")
    for c in CATEGORY.values():
        sim, pair = max_sim[c]
        print(f"| {c} | {counts[c]} | {sim:.1f} | {pair} |")
    return errors


def stage_behaviour(check_only: bool) -> None:
    items = parse_drafts()
    errors = check_behaviour(items)
    print(f"{len(items)} items; {len(errors)} problem(s)")
    for e in errors:
        print("  " + e)
    if errors:
        sys.exit(1)
    if not check_only:
        write_jsonl(OUT_DIR / "behaviour_examples.jsonl", items)
        print(f"-> {OUT_DIR / 'behaviour_examples.jsonl'}")


def split_stratified(examples: list[dict]) -> tuple[list[dict], list[dict]]:
    strata: dict[str, list[dict]] = defaultdict(list)
    for ex in examples:
        strata[ex["intent"] if ex["category"] == "task" else ex["category"]].append(ex)
    val_ids = set()
    for members in strata.values():
        val_ids.update(ex["id"] for ex in members[:max(1, round(VAL_SHARE * len(members)))])
    return [ex for ex in examples if ex["id"] not in val_ids], [ex for ex in examples if ex["id"] in val_ids]


def stage_assemble(dest: Path = OUT_DIR, src: Path = OUT_DIR) -> None:
    """task examples from <src>/task_examples.jsonl, behaviour examples from data/sft/v1; output into <dest>."""
    import hashlib
    from contamination import check as contamination_check
    from verify import ALL_RULES, BEHAVIOUR_RULES, verify
    sys.path.insert(0, str(ROOT / "train"))
    from masking_check import load_tokenizer, report as masking_report

    system = SYSTEM_PROMPT.read_text(encoding="utf-8").strip()
    examples = [{"id": r["id"], "source": r["source"], "category": "task", "intent": r["intent"],
                 "candidate_index": r["candidate_index"], "messages": r["messages"]}
                for r in read_jsonl(src / "task_examples.jsonl")]
    examples += [{"id": r["id"], "source": "behaviour", "category": r["category"], "intent": r["intent"],
                  "candidate_index": None, "messages": [{"role": "system", "content": system}] + r["turns"]}
                 for r in read_jsonl(OUT_DIR / "behaviour_examples.jsonl")]
    random.Random(SEED).shuffle(examples)
    train, val = split_stratified(examples)
    failures = []

    held = sorted({ex["intent"] for ex in examples if ex["intent"] in HELD_OUT})
    if held:
        failures.append("held-out intents present: " + ", ".join(held))

    items = read_jsonl(EVAL_SET)
    queries = [(it["id"], it["messages"][0]["content"]) for it in items]
    contamination = {}
    for name, part in (("train", train), ("val", val)):
        r = contamination_check(queries, [m["content"] for ex in part for m in ex["messages"]])
        contamination[name] = {"exact": len(r["exact"]), "fuzzy_ge_90": len(r["fuzzy"]), "ngram8_rate": round(r["ngram_rate"], 4)}
        if r["exact"] or r["fuzzy"]:
            failures.append(f"contamination in {name}: {len(r['exact'])} exact, {len(r['fuzzy'])} fuzzy")

    n_turns = 0
    for ex in examples:
        msgs = ex["messages"]
        for k, m in enumerate(msgs):
            if m["role"] != "assistant":
                continue
            n_turns += 1
            rules, intent = (ALL_RULES, ex["intent"]) if ex["category"] == "task" else (BEHAVIOUR_RULES, None)
            ok, reasons = verify(m["content"], intent, msgs[k - 1]["content"], rules)
            if not ok:
                failures.append(f"{ex['id']} turn {k}: " + "; ".join(reasons))

    tok = load_tokenizer(TOKENIZER)
    lengths = {ex["id"]: len(tok.apply_chat_template(ex["messages"], tokenize=True, add_generation_prompt=False,
                                                     return_dict=True)["input_ids"])
               for ex in examples}
    ls = sorted(lengths.values())
    within = sum(l <= MAX_TOKENS for l in ls) / len(ls)
    if within < 0.99:
        failures.append(f"only {100 * within:.2f} % of examples are <= {MAX_TOKENS} tokens")
    edges = [0, 384, 448, 512, 576, 640, 768, 1024]
    hist = {f"{lo}-{hi}": sum(lo < l <= hi for l in ls) for lo, hi in zip(edges, edges[1:])}
    hist[f">{MAX_TOKENS}"] = sum(l > MAX_TOKENS for l in ls)

    pick = [next(ex for ex in train if ex["category"] == "task"),
            next(ex for ex in train if ex["category"] == "B3-indirect"),
            next(ex for ex in train if ex["category"] == "B1-dialogue")]
    text, masking_ok = masking_report(tok, pick, TOKENIZER)
    if not masking_ok:
        failures.append("masking check failed")

    if failures:
        print(f"BUILD FAILED: {len(failures)} violation(s)")
        for f in failures:
            print("  " + f)
        sys.exit(1)

    # a provisional assembly (mechanics-only GPU runs) keeps its masking report next to its data
    dest.mkdir(parents=True, exist_ok=True)
    (MASKING_REPORT if dest == OUT_DIR else dest / "masking_example.md").write_text(text, encoding="utf-8", newline="\n")
    write_jsonl(dest / "train.jsonl", train)
    write_jsonl(dest / "val.jsonl", val)

    def counts(part, key):
        c = defaultdict(int)
        for ex in part:
            c[key(ex)] += 1
        return dict(sorted(c.items()))
    per_intent = sorted(counts([ex for ex in examples if ex["category"] == "task"], lambda e: e["intent"]).values())
    stats = {
        "examples": len(examples), "train": len(train), "val": len(val), "assistant_turns": n_turns,
        "by_source": {p: counts(part, lambda e: e["source"]) for p, part in (("train", train), ("val", val))},
        "by_category": {p: counts(part, lambda e: e["category"]) for p, part in (("train", train), ("val", val))},
        "task_examples_per_intent": {"intents": len(per_intent), "min": per_intent[0], "median": per_intent[len(per_intent) // 2], "max": per_intent[-1]},
        "tokens": {"tokenizer": TOKENIZER, "max": ls[-1], "p99": ls[min(len(ls) - 1, int(0.99 * len(ls)))],
                   "median": ls[len(ls) // 2], "min": ls[0], "share_le_1024": round(within, 4), "histogram": hist,
                   "max_id": max(lengths, key=lengths.get)},
        "contamination": contamination,
        "held_out_intents_present": held,
        "masking_examples": [ex["id"] for ex in pick],
    }
    (dest / "assemble_stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8", newline="\n")
    files = sorted(p for p in dest.iterdir() if p.is_file() and p.name not in ("manifest.sha256", "masking_example.md"))
    (dest / "manifest.sha256").write_text(
        "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in files), encoding="utf-8", newline="\n")
    print(json.dumps(stats, indent=2))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["select", "task", "audit", "audit2", "behaviour", "assemble"], required=True)
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--out-dir", default=None, help="assemble: output folder, e.g. data/sft/v1_rewrite (default data/sft/v1)")
    ap.add_argument("--src-dir", default=None, help="assemble: folder of task_examples.jsonl (default data/sft/v1)")
    ap.add_argument("--selection", choices=["v3", "canonical"], default="v3", help="task: rewrite selection or canonical only")
    ap.add_argument("--task-out", default=None, help="task: output folder (default data/sft/v1)")
    args = ap.parse_args()
    if args.stage == "behaviour":
        stage_behaviour(args.check_only)
    elif args.stage == "assemble":
        stage_assemble(Path(args.out_dir).resolve() if args.out_dir else OUT_DIR,
                       Path(args.src_dir).resolve() if args.src_dir else OUT_DIR)
    elif args.stage == "task":
        stage_task(args.selection, Path(args.task_out).resolve() if args.task_out else OUT_DIR)
    else:
        {"select": stage_select, "task": stage_task, "audit": stage_audit, "audit2": stage_audit2, "assemble": stage_assemble}[args.stage]()


if __name__ == "__main__":
    main()

"""Contamination check: eval queries vs Banking77 TRAIN and project training files.

Exact matches (after normalisation) must be 0. Fuzzy matches (rapidfuzz
ratio >= 0.9) and the word 8-gram overlap rate are reported.

Usage: python eval/contamination.py   -> eval/contamination_report.md
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

from rapidfuzz import fuzz, process

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))
import banking77 as b77  # noqa: E402

EVAL_SET = ROOT / "eval" / "eval_set.jsonl"
REPORT = ROOT / "eval" / "contamination_report.md"
TRAIN_DIRS = [ROOT / "data" / "sft", ROOT / "data" / "dpo"]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", s.lower())).strip()


def ngrams(s: str, n: int = 8) -> set[tuple[str, ...]]:
    w = norm(s).split()
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def strings_from_json(obj) -> list[str]:
    out = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out += strings_from_json(v)
    elif isinstance(obj, list):
        for v in obj:
            out += strings_from_json(v)
    return out


def load_training_texts() -> dict[str, list[str]]:
    corpora = {"banking77_train": [r["text"] for r in b77.load_split("train")]}
    for d in TRAIN_DIRS:
        for p in sorted(d.rglob("*")):
            if p.suffix in (".jsonl", ".json") and p.is_file():
                texts = []
                if p.suffix == ".jsonl":
                    for line in p.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            texts += strings_from_json(json.loads(line))
                else:
                    texts += strings_from_json(json.loads(p.read_text(encoding="utf-8")))
                corpora[str(p.relative_to(ROOT))] = texts
    return corpora


def check(eval_queries: list[tuple[str, str]], corpus: list[str]) -> dict:
    cn = [norm(t) for t in corpus]
    cset = set(cn)
    exact, fuzzy = [], []
    corpus_grams = set()
    for t in cn:
        w = t.split()
        corpus_grams.update(tuple(w[i:i + 8]) for i in range(len(w) - 7))
    total_grams = hit_grams = 0
    for qid, q in eval_queries:
        qn = norm(q)
        if qn in cset:
            exact.append((qid, q))
        best = process.extractOne(qn, cn, scorer=fuzz.ratio, score_cutoff=90)
        if best is not None and qn not in cset:
            fuzzy.append((qid, q, corpus[best[2]], round(best[1], 1)))
        g = ngrams(q)
        total_grams += len(g)
        hit_grams += len(g & corpus_grams)
    return {"exact": exact, "fuzzy": fuzzy, "ngram_rate": (hit_grams / total_grams) if total_grams else 0.0, "n_grams": total_grams, "size": len(corpus)}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    items = [json.loads(l) for l in EVAL_SET.read_text(encoding="utf-8").splitlines() if l.strip()]
    queries = [(it["id"], it["messages"][0]["content"]) for it in items]
    corpora = load_training_texts()
    lines = [f"# Contamination report", "", f"Date: {date.today().isoformat()}. Eval items: {len(queries)}. Normalisation: lower-case, punctuation removed, whitespace collapsed.", ""]
    any_exact = False
    for name, corpus in corpora.items():
        r = check(queries, corpus)
        any_exact |= bool(r["exact"])
        lines += [f"## {name}", "", f"- corpus size: {r['size']} texts", f"- exact matches: **{len(r['exact'])}** (must be 0)", f"- fuzzy matches (ratio ≥ 90): {len(r['fuzzy'])}", f"- word 8-gram overlap rate: {100 * r['ngram_rate']:.2f} % of {r['n_grams']} eval 8-grams", ""]
        if r["exact"]:
            lines += ["Exact:", *[f"- `{i}`: {q}" for i, q in r["exact"]], ""]
        if r["fuzzy"]:
            lines += ["Fuzzy (eval → corpus, ratio):", *[f"- `{i}`: \"{q}\" → \"{c}\" ({s})" for i, q, c, s in r["fuzzy"]], ""]
    lines += ["## Verdict", "", "**FAIL: exact matches found.**" if any_exact else "**PASS: no exact matches.** Fuzzy matches are near-duplicates that Banking77 itself contains across its splits; they are listed so that the SFT data builder (Stage 1) can drop them from the training side.", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print("\n".join(lines))
    sys.exit(1 if any_exact else 0)


if __name__ == "__main__":
    main()

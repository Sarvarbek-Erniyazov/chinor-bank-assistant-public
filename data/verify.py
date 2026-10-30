"""Fact and safety verification of generated SFT answers.

A text is accepted only if
  (a) every required fact of its intent is present (eval/score.py normalisation; "->" and "→" are equal),
  (b) v2: every numeric token appears in the intent's canonical answer or in the user message
      (v1: in handbook/handbook.md or in the user message, as eval/score.py),
  (c) there is no hard violation under rubric v1.2,
  (d) no forbidden keyword of its intent is present,
  (e) it has 15-120 words,
  (f) it contains no role tags or template tokens; v2 also no markdown (**, # headings, bullet or numbered lists),
  (g) v2 only: at most 30 % of the reply's distinct content words (lower-cased, stemmed, stopwords removed)
      are missing from all of: canonical answer, user message, system prompt.
Version 2 is the operative one (C1 decision after the GPU smoke run); version 1 is kept for the comparison.
Behaviour turns have no intent and no canonical answer: they are checked with rules (b)-(f), where (b)
falls back to handbook ∪ user message.

Usage: python data/verify.py --rewrites results/c1-rewrites/rewrites_raw.jsonl [--version 1|2]
       -> results/c1-rewrites/verdicts_v<N>.jsonl (id, candidate_index, accept, reasons) and a summary.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from score import fact_present, hard_violation_sentences, normalise, numbers_in  # noqa: E402

HANDBOOK = ROOT / "handbook" / "handbook.md"
SYSTEM_PROMPT = ROOT / "handbook" / "system_prompt.txt"
INTENTS = ROOT / "handbook" / "intents.yaml"
PROMPTS = ROOT / "data" / "sft" / "v1" / "task_prompts.jsonl"

ALL_RULES = "abcdefg"
BEHAVIOUR_RULES = "bcdef"
MIN_WORDS, MAX_WORDS = 15, 120
MAX_UNSUPPORTED = 0.30
TEMPLATE_TOKENS = re.compile(
    r"<\|[^|>]*\|>|</?think>|\[/?INST\]|</?s>|\{[a-z_]+\}"
    r"|^\s*\**(?:system|user|assistant|customer|agent|human|bot)\**\s*:"
    r"|^\s*\[(?:system|user|assistant|customer|agent|human|bot)\]",
    re.I | re.M)
MARKDOWN = re.compile(r"\*\*|__|^\s{0,3}#{1,6}\s|^\s*[-*•+]\s+\S|^\s*\d{1,2}[.)]\s+\S", re.M)

# rule (g): a small fixed stopword list and a light suffix stemmer (no extra dependency)
STOPWORDS = set("""a about above after again against all am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have having he her
here hers him his how i if in into is it its itself just me more most my no nor not now of off on once only or other
our ours out over own same she should so some such than that the their theirs them then there these they this those
through to too under until up very was we were what when where which while who whom why will with would you your
yours also may might must shall s t don't can't won't isn't aren't doesn't didn't i'm you're it's that's there's
let us get got one yes ok please""".split())
WORD = re.compile(r"[a-z][a-z'-]*")


SUFFIXES = [("ational", "ate"), ("tional", "tion"), ("ization", "ize"), ("ation", "ate"), ("ator", "ate"),
            ("iveness", "ive"), ("fulness", "ful"), ("ousness", "ous"), ("ements", ""), ("ement", ""),
            ("ments", ""), ("ment", ""), ("ness", ""), ("ings", ""), ("ing", ""), ("edly", ""), ("ied", "y"),
            ("ies", "y"), ("ers", ""), ("er", ""), ("ed", ""), ("ly", ""), ("es", ""), ("s", "")]


def stem(w: str) -> str:
    """Light suffix stemmer: activation / activate / activated -> activat, scanning -> scan, minutes -> minut."""
    w = w.strip("'-")
    if w.endswith("'s"):
        w = w[:-2]
    for suf, rep in SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[:-len(suf)] + rep
            break
    if w.endswith("e") and len(w) > 4:
        w = w[:-1]
    if len(w) > 3 and w[-1] == w[-2] and w[-1] not in "lsz":
        w = w[:-1]
    return w


def content_stems(text: str) -> set[str]:
    return {stem(w) for w in WORD.findall(text.lower().replace("’", "'")) if w not in STOPWORDS and len(w) > 1}


_SYSTEM_STEMS = content_stems(SYSTEM_PROMPT.read_text(encoding="utf-8"))

_HANDBOOK_NUMBERS = numbers_in(HANDBOOK.read_text(encoding="utf-8"))
_INTENTS = None


def intents() -> dict:
    global _INTENTS
    if _INTENTS is None:
        _INTENTS = yaml.safe_load(INTENTS.read_text(encoding="utf-8"))
    return _INTENTS


def forbidden_hits(forbidden: list[str], text_norm: str) -> list[str]:
    # a purely numeric keyword ("18") matches on digit boundaries, like a numeric required fact
    return [f for f in forbidden if fact_present(f, text_norm)]


def unsupported_share(text: str, canonical: str, user: str) -> tuple[float, list[str]]:
    words = content_stems(text)
    support = content_stems(canonical) | content_stems(user) | _SYSTEM_STEMS
    missing = sorted(words - support)
    return (len(missing) / len(words) if words else 0.0), missing


def verify(text: str, intent: str | None = None, user: str = "", rules: str = ALL_RULES,
           required_facts: list[str] | None = None, forbidden: list[str] | None = None,
           version: int = 2) -> tuple[bool, list[str]]:
    """Return (accept, reasons). reasons holds one entry per failed rule, prefixed with its letter."""
    if version == 1:
        rules = rules.replace("g", "")
    entry = intents().get(intent, {}) if intent else {}
    canonical = entry.get("canonical_answer")
    facts = required_facts if required_facts is not None else entry.get("required_facts", [])
    forb = forbidden if forbidden is not None else entry.get("forbidden", [])
    tn = normalise(text)
    reasons = []
    if "a" in rules:
        missing = [f for f in facts if not fact_present(f, tn)]
        if missing:
            reasons.append("a missing facts: " + "; ".join(missing))
    if "b" in rules:
        # numbers echoed from the customer are not fabrications (ADR-018)
        if version >= 2 and canonical is not None:
            allowed, where = numbers_in(canonical) | numbers_in(user), "canonical answer"
        else:
            allowed, where = _HANDBOOK_NUMBERS | numbers_in(user), "handbook"
        bad = sorted(n for n in numbers_in(text) if n not in allowed)
        if bad:
            reasons.append(f"b numbers not in {where} or user message: " + ", ".join(bad))
    if "c" in rules:
        hv = hard_violation_sentences(text, user)
        if hv:
            reasons.append("c hard violation: " + " | ".join(hv))
    if "d" in rules:
        hit = forbidden_hits(forb, tn)
        if hit:
            reasons.append("d forbidden: " + "; ".join(hit))
    if "e" in rules:
        n = len(text.split())
        if not MIN_WORDS <= n <= MAX_WORDS:
            reasons.append(f"e length: {n} words")
    if "f" in rules:
        m = TEMPLATE_TOKENS.search(text)
        if m:
            reasons.append(f"f template token: {m.group(0).strip()!r}")
        elif version >= 2 and (m := MARKDOWN.search(text)):
            reasons.append(f"f markdown: {m.group(0).strip()!r}")
    if "g" in rules and version >= 2 and canonical is not None:
        share, missing = unsupported_share(text, canonical, user)
        if share > MAX_UNSUPPORTED:
            reasons.append(f"g unsupported content words: {100 * share:.0f} % ({', '.join(missing[:12])})")
    return not reasons, reasons


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--rewrites", default=str(ROOT / "results" / "c1-rewrites" / "rewrites_raw.jsonl"))
    ap.add_argument("--prompts", default=str(PROMPTS))
    ap.add_argument("--version", type=int, choices=[1, 2], default=2)
    ap.add_argument("--out", default=None, help="default: verdicts_v<version>.jsonl next to --rewrites")
    args = ap.parse_args()
    prompts = {r["id"]: r for r in map(json.loads, Path(args.prompts).read_text(encoding="utf-8").splitlines())}
    rows = [json.loads(l) for l in Path(args.rewrites).read_text(encoding="utf-8").splitlines() if l.strip()]
    out = Path(args.out) if args.out else Path(args.rewrites).with_name(f"verdicts_v{args.version}.jsonl")
    verdicts, per_rule = [], Counter()
    for r in rows:
        p = prompts[r["id"]]
        ok, reasons = verify(r["text"], p["intent"], p["query"], version=args.version)
        verdicts.append({"id": r["id"], "candidate_index": r["candidate_index"], "accept": ok, "reasons": reasons})
        per_rule.update({x[0] for x in reasons})
    out.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in verdicts), encoding="utf-8", newline="\n")
    n_ok = sum(v["accept"] for v in verdicts)
    print(f"v{args.version}: {n_ok}/{len(verdicts)} candidates accepted; failures per rule: {dict(sorted(per_rule.items()))}; -> {out}")


if __name__ == "__main__":
    main()

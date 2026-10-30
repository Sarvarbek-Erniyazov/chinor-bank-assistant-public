"""Preference stage §3: rule labels and rule pairs from the on-policy samples (C4). CPU.

python data/pref/label_rules.py --samples <dir>/samples.jsonl [--out data/pref/v1]
Per sample, flags (a sample passes when it has none):
  hard_violation    rubric v1.3 (eval/score.py hard_violation)
  wrong_topic       task prompts: similarity (rapidfuzz ratio / 100 on eval/score.py normalise) to another training
                    intent's canonical answer exceeds the similarity to its own by >= 0.1, or is >= 0.9
  dropped_branch    task prompts of a branching intent (BRANCHES: the canonical answer lists the facts for several slot
                    values) whose user turn names no branch: the facts of some branches but not all, and no question
  missing_fact      task prompts: a required fact of the intent (handbook/intents.yaml) is absent (score.fact_present)
  fabricated_number a number that is neither in the reference (canonical answer / SFT reply) nor in the user turns
  no_stop           the sample did not end on <|im_end|>
  markdown          bold, headings, bullet or numbered lists, code
  too_long          more than 120 words
  behaviour         behaviour prompts, the matching eval rule written generically (no eval-v1 or red-team text):
                    B1: asks a question that names the slot (a content word of the SFT reply's question);
                    B1-dialogue (the reply after the customer gave the detail): no question and every number of the
                    SFT reply present; B2: decline marker + handoff marker; B3-unsafe: refusal marker (eval markers or REFUSE);
                    B3-direct / B3-indirect: refusal or warning cue and none of the system prompt's section headings
                    (a prompt leak); B4: an AI/assistant marker, no claim to be human, no promise; handoff: handoff marker.
Pairs (one per prompt with at least one passing and one failing sample): chosen = the passing sample whose word count
is closest to the median of the passing ones (lowest k on ties); rejected = a failing sample with the highest-priority
failure (PRIORITY; seeded choice among equals). Length balance: pairs are dropped at random (seed 20261029) from the
side that is over-represented until the chosen response is the shorter one in 45-55 % of pairs.
Writes <out>/pairs_rules.jsonl, <out>/labels.jsonl (flags per sample) and <out>/DATA_CARD.md.
--v2 (pairs_v2, ADR-032): rejected candidates are only failing samples whose token-length ratio chosen / rejected is
within 0.6-1.7 and which are not identical to the chosen one after lower-casing and removing punctuation and
whitespace; among them the highest-priority failure, then the closest token length (lowest k on ties). A prompt with
no such candidate gives no pair (counted per reason). Writes <out>/pairs_v2.jsonl and <out>/DATA_CARD_v2.md instead.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))
from build_eval import HELD_OUT  # noqa: E402
from score import HANDOFF, PROMISE, REFUSAL_EXTRA, clean_answer, declines, fact_present, hard_violation, normalise, numbers_in  # noqa: E402

SEED = 20261029
MAX_WORDS = 120
PRIORITY = ["hard_violation", "wrong_topic", "dropped_branch", "missing_fact", "fabricated_number", "no_stop", "other"]
OTHER = {"markdown", "too_long", "behaviour"}
# intent: {branch: (user keywords naming the branch, facts all of which the branch needs)}; from the canonical answers
_PLAN = {"Standard": (r"\bstandard\b", None), "Plus": (r"\bplus\b", None)}
_DOM, _INT = r"\b(domestic|local|uzbek|within uzbekistan)\b", r"\b(international|swift|abroad|foreign|overseas|another country)\b"
_SPEED = {"standard": r"\b(standard|normal|regular)\b", "express": r"\b(express|fast|faster|quick|quicker|urgent)\b"}
_CARD = {"debit card": r"\bdebit\b", "credit card": r"\bcredit\b"}
BRANCHES: dict[str, dict[str, tuple[str, list[str]]]] = {
    "atm_support": {"Standard": (_PLAN["Standard"][0], ["2,500,000"]), "Plus": (_PLAN["Plus"][0], ["6,000,000"])},
    "cash_withdrawal_charge": {"Standard": (_PLAN["Standard"][0], ["2,500,000"]), "Plus": (_PLAN["Plus"][0], ["6,000,000"])},
    "exchange_charge": {"Standard": (_PLAN["Standard"][0], ["15,000,000"]), "Plus": (_PLAN["Plus"][0], ["unlimited"])},
    "getting_spare_card": {"Standard": (_PLAN["Standard"][0], ["35,000"]), "Plus": (_PLAN["Plus"][0], ["plus"])},
    "cancel_transfer": {"domestic": (_DOM, ["scheduled"]), "international": (_INT, ["24 hours", "90,000"])},
    "transfer_fee_charged": {"domestic": (_DOM, ["2,500"]), "international": (_INT, ["0.8 %", "60,000"])},
    "receiving_money": {"domestic": (_DOM, ["00099"]), "international": (_INT, ["CHNRUZTA"])},
    "pending_transfer": {"domestic": (_DOM, ["16:30"]), "international": (_INT, ["2–4 business days"])},
    "transfer_not_received_by_recipient": {"domestic": (_DOM, ["16:30"]), "international": (_INT, ["2–4 business days"])},
    "transfer_into_account": {"domestic": (_DOM, ["16:30"]), "international": (_INT, ["1 business day"])},
    "transfer_timing": {"between Chinor accounts": (r"\b(chinor to chinor|between chinor|another chinor)\b", ["instant"]),
                        "other Uzbek bank": (_DOM, ["16:30"]), "international": (_INT, ["2–4 business days"])},
    "card_delivery_estimate": {"standard": (_SPEED["standard"], ["7 business days"]), "express": (_SPEED["express"], ["2 business days", "45,000"])},
    "get_physical_card": {"standard": (_SPEED["standard"], ["7 business days"]), "express": (_SPEED["express"], ["2 business days", "45,000"])},
    "order_physical_card": {"standard": (_SPEED["standard"], ["7 business days"]), "express": (_SPEED["express"], ["2 business days", "45,000"])},
    "automatic_top_up": {"debit card": (_CARD["debit card"], ["free"]), "credit card": (_CARD["credit card"], ["1.1 %"])},
    "topping_up_by_card": {"debit card": (_CARD["debit card"], ["free"]), "credit card": (_CARD["credit card"], ["1.1 %"])},
}
MARKDOWN = re.compile(r"\*\*|__|`|^\s{0,3}#{1,6}\s|^\s*[-*•]\s|^\s*\d+[.)]\s", re.M)
WARN = re.compile(r"\b(scam|fraud|phishing|never share|do not share|don't share|not legitimate|not genuine|suspicious|"
                  r"official channel|do not send|don't send|be careful)\b", re.I)
REFUSE = re.compile(r"\b(can't|cannot|can not|won't|will not|am not able to|unable to)\s+(share|reveal|disclose|provide|"
                    r"give|show|print|follow|do that|help with that|comply)\b", re.I)
AI_MARK = re.compile(r"\b(AI|assistant|virtual|automated|not a human|not human)\b", re.I)
HUMAN_CLAIM = re.compile(r"\b(I am|I'm) (a )?(real )?(person|human|employee|staff member)\b", re.I)
STOP = set("about after again also another because before being could does doing from have having here into just "
           "know like need please should that their there these they this those what when where which while with would "
           "your yours you're whether which tell let".split())


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def context() -> dict:
    canon = yaml.safe_load((ROOT / "handbook" / "intents.yaml").read_text(encoding="utf-8"))
    canon = {k: v for k, v in canon.items() if k not in HELD_OUT}
    system = (ROOT / "handbook" / "system_prompt.txt").read_text(encoding="utf-8")
    # leak markers: the system prompt's section headings with their colon ("Scope:"), not the bare words
    heads = [m.group(1).strip() + ":" for m in re.finditer(r"^([A-Z][^\n:]{2,40}):", system, re.M)]
    return {"canon": canon, "canon_norm": {k: normalise(v["canonical_answer"]) for k, v in canon.items()}, "leak": heads}


def similarity(a: str, b: str) -> float:
    return fuzz.ratio(a, b) / 100


def wrong_topic(text_norm: str, intent: str, ctx: dict) -> bool:
    sims = {k: similarity(text_norm, c) for k, c in ctx["canon_norm"].items()}
    own = sims.pop(intent)
    other = max(sims.values())
    return other - own >= 0.1 or other >= 0.9


def dropped_branch(text: str, user: str, intent: str) -> bool:
    br = BRANCHES.get(intent)
    if not br or "?" in text or any(re.search(kw, user, re.I) for kw, _ in br.values()):
        return False
    tn = normalise(text)
    covered = [b for b, (_, facts) in br.items() if all(fact_present(f, tn) for f in facts)]
    return 0 < len(covered) < len(br)


def slot_words(reference: str) -> set[str]:
    qs = [s for s in re.split(r"(?<=[.?!])\s+", reference) if s.strip().endswith("?")]
    return {w for q in qs for w in re.findall(r"[a-z][a-z-]{3,}", q.lower()) if w not in STOP}


def behaviour_ok(p: dict, text: str, ctx: dict) -> bool:
    cat, tn = p["category"], normalise(text)
    if cat == "B1":
        qs = [s for s in re.split(r"(?<=[.?!])\s+", text) if "?" in s]
        return bool(qs) and bool(slot_words(p["reference"]) & set(re.findall(r"[a-z][a-z-]{3,}", " ".join(qs).lower())))
    if cat == "B1-dialogue":
        return "?" not in text and all(n in numbers_in(text) for n in numbers_in(p["reference"]))
    if cat == "B2":
        return declines(text) and bool(HANDOFF.search(text))
    if cat == "B3-unsafe":
        return declines(text) or bool(REFUSAL_EXTRA.search(text)) or bool(REFUSE.search(text))
    if cat in ("B3-direct", "B3-indirect"):
        leaked = any(normalise(h) in tn for h in ctx["leak"])
        return (declines(text) or bool(REFUSAL_EXTRA.search(text)) or bool(REFUSE.search(text)) or bool(WARN.search(text)))             and not leaked
    if cat == "B4":
        return bool(AI_MARK.search(text)) and not HUMAN_CLAIM.search(text) and not PROMISE.search(text)
    if cat == "handoff":
        return bool(HANDOFF.search(text))
    raise ValueError(cat)


def flags(p: dict, s: dict, ctx: dict) -> list[str]:
    text = clean_answer(s["raw"])
    tn = normalise(text)
    users = " ".join(m["content"] for m in p["messages"] if m["role"] == "user")
    last_user = [m["content"] for m in p["messages"] if m["role"] == "user"][-1]
    ref = ctx["canon"][p["intent"]]["canonical_answer"] if p["category"] == "task" else p["reference"]
    out = []
    if not text or hard_violation(text, last_user):
        out.append("hard_violation" if text else "behaviour")
    if p["category"] == "task":
        if wrong_topic(tn, p["intent"], ctx):
            out.append("wrong_topic")
        if dropped_branch(text, users, p["intent"]):
            out.append("dropped_branch")
        if any(not fact_present(f, tn) for f in ctx["canon"][p["intent"]]["required_facts"]):
            out.append("missing_fact")
    elif not behaviour_ok(p, text, ctx):
        out.append("behaviour")
    allowed = numbers_in(ref) | numbers_in(users)
    if any(n not in allowed for n in numbers_in(text)):
        out.append("fabricated_number")
    if s["stop_reason"] != "im_end":
        out.append("no_stop")
    if MARKDOWN.search(text):
        out.append("markdown")
    if len(text.split()) > MAX_WORDS:
        out.append("too_long")
    return out


def failure_type(fl: list[str]) -> str:
    for t in PRIORITY[:-1]:
        if t in fl:
            return t
    return "other"


RATIO = (0.6, 1.7)


def norm_text(t: str) -> str:
    return re.sub(r"[\W_]+", "", t.lower())


def make_pair(p: dict, labelled: list[tuple[dict, list[str]]], rng: random.Random, v2: bool = False,
              why: Counter | None = None) -> dict | None:
    ok = [s for s, f in labelled if not f]
    bad = [(s, f) for s, f in labelled if f]
    if not ok or not bad:
        return None
    words = lambda s: len(clean_answer(s["raw"]).split())
    med = st.median(words(s) for s in ok)
    chosen = min(ok, key=lambda s: (abs(words(s) - med), s["k"]))
    if v2:
        ntok = lambda s: s.get("n_tokens") or len(clean_answer(s["raw"]).split())
        same = [(s, f) for s, f in bad if norm_text(clean_answer(s["raw"])) == norm_text(clean_answer(chosen["raw"]))]
        bad = [(s, f) for s, f in bad if (s, f) not in same]
        inb = [(s, f) for s, f in bad if RATIO[0] <= ntok(chosen) / max(1, ntok(s)) <= RATIO[1]]
        if not inb:
            if why is not None:
                why["near_identical" if not bad else "length_ratio"] += 1
            return None
        rank = min(PRIORITY.index(failure_type(f)) for _, f in inb)
        rej, rf = min(((s, f) for s, f in inb if PRIORITY.index(failure_type(f)) == rank),
                      key=lambda x: (abs(ntok(x[0]) - ntok(chosen)), x[0]["k"]))
    else:
        rank = min(PRIORITY.index(failure_type(f)) for _, f in bad)
        rej, rf = rng.choice([(s, f) for s, f in bad if PRIORITY.index(failure_type(f)) == rank])
    return {"id": p["id"], "source": p["source"], "category": p["category"], "intent": p["intent"], "messages": p["messages"],
            "chosen": clean_answer(chosen["raw"]), "rejected": clean_answer(rej["raw"]), "chosen_k": chosen["k"],
            "rejected_k": rej["k"], "failure_type": failure_type(rf), "rejected_flags": rf,
            "chosen_words": words(chosen), "rejected_words": words(rej)}


def shorter_share(pairs: list[dict]) -> float:
    return sum(p["chosen_words"] < p["rejected_words"] for p in pairs) / len(pairs) if pairs else float("nan")


def balance(pairs: list[dict], rng: random.Random, lo: float = 0.45, hi: float = 0.55) -> list[dict]:
    """Drop random pairs from the over-represented side until lo <= share(chosen shorter) <= hi."""
    keep = list(pairs)
    while keep and not lo <= shorter_share(keep) <= hi:
        side = shorter_share(keep) > hi  # True: too many chosen-shorter pairs
        cand = [i for i, p in enumerate(keep) if (p["chosen_words"] < p["rejected_words"]) == side]
        keep.pop(rng.choice(cand))
    return keep


def describe(xs: list[int]) -> str:
    if not xs:
        return "—"
    q = st.quantiles(xs, n=4) if len(xs) > 1 else [xs[0]] * 3
    return f"median {st.median(xs):.0f}, IQR {q[0]:.0f}–{q[2]:.0f}, mean {st.mean(xs):.1f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", required=True)
    ap.add_argument("--prompts", default=str(ROOT / "data" / "pref" / "v1" / "prompts.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "data" / "pref" / "v1"))
    ap.add_argument("--v2", action="store_true", help="pairs_v2: length-ratio bound and near-identical drop")
    a = ap.parse_args()
    out = Path(a.out)
    ctx = context()
    prompts = {p["id"]: p for p in jsonl(Path(a.prompts))}
    by = defaultdict(list)
    for s in jsonl(Path(a.samples)):
        by[s["id"]].append(s)
    rng = random.Random(SEED)
    labels, pairs, outcome, why = [], [], Counter(), Counter()
    flag_counts = Counter()
    for pid, p in prompts.items():
        lab = [(s, flags(p, s, ctx)) for s in sorted(by[pid], key=lambda s: s["k"])]
        for s, f in lab:
            labels.append({"id": pid, "k": s["k"], "flags": f})
            flag_counts.update(f or ["pass"])
        pr = make_pair(p, lab, rng, a.v2, why)
        outcome["pair" if pr else ("all_pass" if all(not f for _, f in lab) else "all_fail")] += 1
        outcome[f"{'pair' if pr else 'no_pair'}:{p['source']}"] += 1
        if pr:
            pairs.append(pr)
    before = shorter_share(pairs)
    bal = balance(pairs, random.Random(SEED))
    for name, rows in (("labels.jsonl", labels), ("pairs_v2.jsonl" if a.v2 else "pairs_rules.jsonl", bal)):
        (out / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")
    card = data_card(prompts, labels, flag_counts, outcome, pairs, bal, before)
    if a.v2:
        card = card.replace("# Preference data v1: rule pairs (C4 §3)", "# Preference data v2: rule pairs with a length-ratio bound (ADR-032)")
        card += (f"\n## v2 filters\n\nRejected candidates limited to token-length ratio chosen / rejected in {RATIO[0]}–{RATIO[1]} "
                 f"and not identical to the chosen one after normalising case, punctuation and whitespace. Prompts that lost "
                 f"their pair: length ratio {why['length_ratio']:,}, near-identical {why['near_identical']:,}. Pairs before "
                 f"length balance {len(pairs):,}, final {len(bal):,} (v1: 371 / 348).\n")
    (out / ("DATA_CARD_v2.md" if a.v2 else "DATA_CARD.md")).write_text(card, encoding="utf-8", newline="\n")
    print(card)


def data_card(prompts, labels, flag_counts, outcome, pairs, bal, before) -> str:
    n = len(labels)
    L = ["# Preference data v1: rule pairs (C4 §3)", "",
         "`data/pref/label_rules.py`. On-policy samples from sft-merged (14B rsLoRA v1.2 seed 0, merged), K = 8 per prompt "
         "(`data/pref/sample.py`). Prompts: `data/pref/v1/prompts.jsonl` (no eval-v1 or redteam-v1 text: exact 0, fuzzy >= 90 "
         "0). No canonical answer or SFT reply is used as a chosen response.", "",
         f"## Samples: {n:,} ({len(prompts):,} prompts × 8)", "", "| Flag | Samples | % |", "|---|---|---|"]
    L += [f"| {k} | {v:,} | {100 * v / n:.1f} |" for k, v in flag_counts.most_common()]
    L += ["", "A sample can carry several flags; `pass` = no flag.", "",
          "## Pairs", "", f"Prompts with a pair: {outcome['pair']:,}; all samples pass: {outcome['all_pass']:,}; all fail: "
          f"{outcome['all_fail']:,} (no pair for these).", "", "| Source | Prompts | Pairs (before length balance) | Pairs (final) |",
          "|---|---|---|---|"]
    for src in sorted({p["source"] for p in prompts.values()}):
        L.append(f"| {src} | {sum(p['source'] == src for p in prompts.values()):,} | {sum(p['source'] == src for p in pairs):,} | "
                 f"{sum(p['source'] == src for p in bal):,} |")
    L += ["", "| Failure type of the rejected response (priority order) | Pairs (before) | Pairs (final) |", "|---|---|---|"]
    L += [f"| {t} | {sum(p['failure_type'] == t for p in pairs):,} | {sum(p['failure_type'] == t for p in bal):,} |" for t in PRIORITY]
    L += ["", "## Length balance", "",
          f"Share of pairs in which the chosen response is shorter: before {100 * before:.1f} % ({len(pairs):,} pairs), "
          f"after {100 * shorter_share(bal):.1f} % ({len(bal):,} pairs; target 45–55 %).", "",
          "| Words | Before | After |", "|---|---|---|",
          f"| chosen | {describe([p['chosen_words'] for p in pairs])} | {describe([p['chosen_words'] for p in bal])} |",
          f"| rejected | {describe([p['rejected_words'] for p in pairs])} | {describe([p['rejected_words'] for p in bal])} |"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()

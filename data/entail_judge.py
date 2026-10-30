"""Sentence-level entailment filter for SFT rewrites with a non-Qwen judge (ADR-022).

Judge: google/gemma-4-31B-it, bf16, transformers, greedy (temperature 0), JSON output.
Premise = the intent's canonical answer + the customer message, nothing else. Hypothesis = one sentence of the
candidate. Labels: entailed / neutral / contradicted. Hedges ("may", "usually", "in most cases"), added
conditions, channels, contacts, advice and promises are neutral unless the premise states them. A candidate
passes only if every sentence is entailed; an unparsable judge reply counts as neutral.

Validation (C1 audit, 50 rows with manual marks):
  python data/entail_judge.py --audit data/sft/_provisional/judge_audit_50.jsonl --prompt-version 1 --out <dir>
  -> <dir>/judge_audit_v<N>.jsonl (per row: sentences, labels, flagged) and summary_v<N>.json (confusion table;
     pass = flags >= 7 of the 8 marked rows and <= 4 of the 42 unmarked).
Full pass (every candidate accepted by verifier v2):
  python data/entail_judge.py --candidates results/c1-rewrites --prompt-version <validated N> --out <dir>
  -> <dir>/entail_verdicts.jsonl (id, candidate_index, entailed, sentences) and summary_full.json.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

MODEL = "google/gemma-4-31B-it"
SENT = re.compile(r"(?<=[.?!])\s+(?=[A-Z0-9\"'(])")

RULES_V1 = """Decide whether the HYPOTHESIS is fully supported by the PREMISE.
- entailed: everything the hypothesis states is stated in, or follows directly from, the premise.
- contradicted: the hypothesis conflicts with the premise.
- neutral: anything else. In particular, hedges ("may", "usually", "in most cases"), added conditions,
  channels (app screens, chat, phone, branches), contacts, advice and promises are neutral unless the premise
  states them. Rephrasing with the same meaning is entailed."""

RULES_V2 = RULES_V1 + """
- Judge the hypothesis on its own claims. A sentence that repeats premise facts in other words is entailed even
  if it is shorter or differently ordered; a sentence that adds any new claim, qualification or step is neutral."""

TEMPLATE = """{rules}

PREMISE (the bank's approved answer, then the customer's message):
Approved answer: {canonical}
Customer message: {query}

HYPOTHESIS (one sentence of a proposed reply):
{sentence}

Reply with JSON only: {{"label": "entailed" | "neutral" | "contradicted", "reason": "<at most 15 words>"}}"""


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT.split(text.strip()) if s.strip()]


def load_judge(revision: str):
    import torch
    from transformers import AutoProcessor
    try:
        from transformers import AutoModelForImageTextToText as Auto
    except ImportError:
        from transformers import AutoModelForCausalLM as Auto
    proc = AutoProcessor.from_pretrained(MODEL, revision=revision)
    model = Auto.from_pretrained(MODEL, revision=revision, dtype=torch.bfloat16, device_map="cuda")
    model.eval()
    return proc, model


def judge(proc, model, prompts: list[str], batch_size: int) -> list[str]:
    import torch
    tok = getattr(proc, "tokenizer", proc)
    tok.padding_side = "left"
    outs = []
    for s in range(0, len(prompts), batch_size):
        chats = [[{"role": "user", "content": [{"type": "text", "text": p}]}] for p in prompts[s:s + batch_size]]
        enc = proc.apply_chat_template(chats, add_generation_prompt=True, tokenize=True, return_dict=True,
                                       return_tensors="pt", padding=True).to(model.device)
        with torch.no_grad():
            gen = model.generate(**enc, do_sample=False, max_new_tokens=60)
        outs += tok.batch_decode(gen[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)
        print(f"{min(s + batch_size, len(prompts))}/{len(prompts)} judgements", flush=True)
    return outs


def parse(reply: str) -> str:
    m = re.search(r'"label"\s*:\s*"(entailed|neutral|contradicted)"', reply)
    return m.group(1) if m else "unparsed"


def candidate_rows(folder: Path) -> list[dict]:
    """Every v2-accepted candidate with its premise (canonical answer, customer message)."""
    import yaml
    root = Path(__file__).resolve().parents[1]
    intents = yaml.safe_load((root / "handbook" / "intents.yaml").read_text(encoding="utf-8"))
    prompts = {r["id"]: r for r in map(json.loads, (root / "data" / "sft" / "v1" / "task_prompts.jsonl").read_text(encoding="utf-8").splitlines())}
    texts = {(r["id"], r["candidate_index"]): r["text"] for r in map(json.loads, (folder / "rewrites_raw.jsonl").read_text(encoding="utf-8").splitlines())}
    rows = []
    for v in map(json.loads, (folder / "verdicts_v2.jsonl").read_text(encoding="utf-8").splitlines()):
        if v["accept"]:
            p = prompts[v["id"]]
            rows.append({"id": v["id"], "candidate_index": v["candidate_index"], "intent": p["intent"], "query": p["query"],
                         "canonical_answer": intents[p["intent"]]["canonical_answer"],
                         "rewrite": texts[(v["id"], v["candidate_index"])]})
    return rows


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--audit", help="validation: jsonl with manual_unsupported_claim marks")
    mode.add_argument("--candidates", help="full pass: folder with rewrites_raw.jsonl and verdicts_v2.jsonl")
    ap.add_argument("--prompt-version", type=int, choices=[1, 2], default=1)
    ap.add_argument("--revision", default="main")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = ([json.loads(l) for l in Path(a.audit).read_text(encoding="utf-8").splitlines() if l.strip()] if a.audit
            else candidate_rows(Path(a.candidates)))
    rules = {1: RULES_V1, 2: RULES_V2}[a.prompt_version]
    jobs = [(i, s) for i, r in enumerate(rows) for s in sentences(r["rewrite"])]
    prompts = [TEMPLATE.format(rules=rules, canonical=rows[i]["canonical_answer"], query=rows[i]["query"], sentence=s)
               for i, s in jobs]
    t0 = time.time()
    proc, model = load_judge(a.revision)
    load_s = time.time() - t0
    print(f"judge loaded in {load_s:.0f} s: {type(model).__name__}", flush=True)
    t1 = time.time()
    replies = judge(proc, model, prompts, a.batch_size)
    gen_s = time.time() - t1

    per_row = {i: [] for i in range(len(rows))}
    for (i, s), rep in zip(jobs, replies):
        per_row[i].append({"sentence": s, "label": parse(rep), "reply": rep.strip()})
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.candidates:
        n_ok = 0
        with (out / "entail_verdicts.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for i, r in enumerate(rows):
                ok = all(x["label"] == "entailed" for x in per_row[i])
                n_ok += ok
                f.write(json.dumps({"id": r["id"], "candidate_index": r["candidate_index"], "entailed": ok,
                                    "sentences": per_row[i]}, ensure_ascii=False) + "\n")
        summary = {"judge": MODEL, "revision": a.revision, "model_class": type(model).__name__,
                   "prompt_version": a.prompt_version, "candidates": len(rows), "entailed": n_ok,
                   "sentences": len(jobs), "unparsed": sum(parse(r) == "unparsed" for r in replies),
                   "load_s": round(load_s), "generate_s": round(gen_s),
                   "sentences_per_s": round(len(jobs) / max(gen_s, 1e-9), 2)}
        (out / "summary_full.json").write_text(json.dumps(summary, indent=2), encoding="utf-8", newline="\n")
        print(json.dumps(summary, indent=2))
        return
    conf = {"marked_flagged": 0, "marked_passed": 0, "unmarked_flagged": 0, "unmarked_passed": 0}
    with (out / f"judge_audit_v{a.prompt_version}.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for i, r in enumerate(rows):
            flagged = any(x["label"] != "entailed" for x in per_row[i])
            key = ("marked" if r["manual_unsupported_claim"] else "unmarked") + ("_flagged" if flagged else "_passed")
            conf[key] += 1
            f.write(json.dumps({"id": r["id"], "intent": r["intent"], "mark": r["manual_unsupported_claim"],
                                "flagged": flagged, "sentences": per_row[i]}, ensure_ascii=False) + "\n")
    n_marked = conf["marked_flagged"] + conf["marked_passed"]
    summary = {
        "judge": MODEL, "revision": a.revision, "model_class": type(model).__name__, "prompt_version": a.prompt_version,
        "rows": len(rows), "sentences": len(jobs), "unparsed": sum(parse(r) == "unparsed" for r in replies),
        "confusion": conf,
        "pass": conf["marked_flagged"] >= n_marked - 1 and conf["unmarked_flagged"] <= 4,
        "thresholds": f"flag >= {n_marked - 1} of {n_marked} marked, <= 4 of {len(rows) - n_marked} unmarked",
        "load_s": round(load_s), "generate_s": round(gen_s), "sentences_per_s": round(len(jobs) / max(gen_s, 1e-9), 2),
    }
    (out / f"summary_v{a.prompt_version}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

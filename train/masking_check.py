"""Print a token-by-token (token, id, label) table for one chat example.

Usage: python train/masking_check.py [--tokenizer Qwen/Qwen3-0.6B-Base]
       python train/masking_check.py --jsonl data/sft/v1/train.jsonl --ids a,b,c --out docs/masking_example_v1.md
The second form runs the Stage-0 masking checks (train/tests/test_masking.py) on real examples and
writes a markdown report with the token table of each example.
"""
import argparse
import json
from pathlib import Path

from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
IM_END = "<|im_end|>"

EXAMPLE = [
    {"role": "system", "content": "You are the Chinor Bank Assistant."},
    {"role": "user", "content": "What is the contactless limit?"},
    {"role": "assistant", "content": "Contactless payments are limited to 900,000 UZS per tap."},
]


def load_tokenizer(name: str):
    tok = AutoTokenizer.from_pretrained(name)
    tok.chat_template = (ROOT / "train" / "chat_template.jinja").read_text(encoding="utf-8")
    return tok


def labels_for(tok, messages):
    enc = tok.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=False,
        return_assistant_tokens_mask=True, return_dict=True,
    )
    ids, mask = list(enc["input_ids"]), list(enc["assistant_masks"])
    return ids, [i if m == 1 else -100 for i, m in zip(ids, mask)]


def check_masking(tok, messages) -> dict:
    """The three Stage-0 checks: supervised tokens decode to exactly the assistant turns plus <|im_end|>;
    every system/user token is masked; the first supervised token follows '<|im_start|>assistant\\n'."""
    ids, labels = labels_for(tok, messages)
    kept = [i for i in labels if i != -100]
    target = "".join(m["content"] + IM_END for m in messages if m["role"] == "assistant")
    supervised_ok = tok.decode(kept, skip_special_tokens=False) == target
    text = tok.decode(ids, skip_special_tokens=False)
    offsets, pos = [], 0
    for i in ids:
        piece = tok.decode([i], skip_special_tokens=False)
        offsets.append((pos, pos + len(piece)))
        pos += len(piece)
    masked_ok = True
    for m in messages:
        if m["role"] == "assistant":
            continue
        start = text.index(m["content"])
        end = start + len(m["content"])
        masked_ok &= all(lab == -100 for (s, e), lab in zip(offsets, labels) if s < end and e > start)
    starts = [k for k in range(1, len(labels)) if labels[k] != -100 and labels[k - 1] == -100]
    header_ok = all(tok.decode(ids[k - 2:k], skip_special_tokens=False) == "assistant\n"
                    and ids[k - 3] == tok.convert_tokens_to_ids("<|im_start|>") for k in starts)
    return {"ids": ids, "labels": labels, "total": len(ids), "supervised": len(kept),
            "assistant_turns": sum(m["role"] == "assistant" for m in messages), "supervised_spans": len(starts),
            "supervised_equals_assistant_text": supervised_ok, "system_user_masked": masked_ok,
            "header_masked": header_ok}


def table(tok, ids, labels) -> list[str]:
    rows = [f"{'pos':>4} | {'token':<28} | {'id':>7} | label", "-" * 60]
    for k, (i, lab) in enumerate(zip(ids, labels)):
        piece = tok.decode([i], skip_special_tokens=False).replace("\n", "\\n")
        rows.append(f"{k:>4} | {piece!r:<28} | {i:>7} | {lab}")
    return rows


def report(tok, examples: list[dict], tokenizer_name: str) -> tuple[str, bool]:
    lines = ["# Masking check on SFT v1 examples", "",
             f"Stage-0 masking checks (`train/tests/test_masking.py`) run on {len(examples)} real examples from SFT v1 "
             f"with the project template `train/chat_template.jinja` and the `{tokenizer_name}` tokenizer "
             "(identical across Qwen3 sizes). Written by `data/build_sft.py --stage assemble`.", "",
             "| Example | Category | Assistant turns | Supervised spans | Tokens | Supervised | Supervised = assistant text + `<|im_end|>` | System/user masked | Header masked |",
             "|---|---|---|---|---|---|---|---|---|"]
    all_ok = True
    results = []
    for ex in examples:
        r = check_masking(tok, ex["messages"])
        ok = r["supervised_equals_assistant_text"] and r["system_user_masked"] and r["header_masked"] \
            and r["supervised_spans"] == r["assistant_turns"]
        all_ok &= ok
        results.append((ex, r))
        yn = lambda b: "yes" if b else "**NO**"
        lines.append(f"| `{ex['id']}` | {ex['category']} | {r['assistant_turns']} | {r['supervised_spans']} | {r['total']} | {r['supervised']} | "
                     f"{yn(r['supervised_equals_assistant_text'])} | {yn(r['system_user_masked'])} | {yn(r['header_masked'])} |")
    lines += ["", f"Result: **{'PASS' if all_ok else 'FAIL'}**.", ""]
    for ex, r in results:
        lines += [f"## `{ex['id']}` ({ex['category']})", "", "Label -100 = masked; otherwise the label is the token id.", "",
                  "```", *table(tok, r["ids"], r["labels"]), "```", ""]
    return "\n".join(lines), all_ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokenizer", default="Qwen/Qwen3-0.6B-Base")
    ap.add_argument("--jsonl", default=None)
    ap.add_argument("--ids", default=None, help="comma-separated example ids from --jsonl")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    tok = load_tokenizer(args.tokenizer)
    if args.jsonl:
        rows = {r["id"]: r for r in map(json.loads, Path(args.jsonl).read_text(encoding="utf-8").splitlines()) if r}
        text, ok = report(tok, [rows[i] for i in args.ids.split(",")], args.tokenizer)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        print(text.split("\n## ")[0])
        raise SystemExit(0 if ok else 1)
    ids, labels = labels_for(tok, EXAMPLE)
    print("\n".join(table(tok, ids, labels)))
    print("-" * 60)
    n_sup = sum(l != -100 for l in labels)
    print(f"total tokens: {len(ids)}  supervised: {n_sup}  masked: {len(ids) - n_sup}")


if __name__ == "__main__":
    main()

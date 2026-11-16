"""results/gguf_demo_models.md: the 1.7B demo GGUFs (CPU) next to their recorded bf16 Protocol-A runs.

python results/gguf_report.py --decode   (once per new run, needs the cached Qwen/Qwen3-1.7B-Base tokenizer)
python results/gguf_report.py            (scores and the report from committed files only)
--decode turns results/runs/gguf-<name>/generations.jsonl into answers.jsonl (id, raw, stop_reason, latency_ms,
n_tokens): raw = the HF tokenizer's decode of the generated ids, skip_special_tokens=False, as eval/run_eval.py
writes it; decode.json records how many raw texts equal llama.cpp's own detokenisation. Runs that already have
answers.jsonl are left as they are.
The default mode scores answers.jsonl with eval/score.py (rubric v1.3) into scores.jsonl and writes the report:
1. the four served files (SERVED, ADR-036): file, SHA-256, size, Assistant /200, the diagnostic turn-cut Assistant
   /200 (eval/turn_cut.py, as in results/lora_no_token_rows.md; never the official score), retention /20, stop
   reasons, item-level agreement with the recorded run (eval/outputs/<compare_arm>/);
2. every other level run, the "Q4_K_M clearly worse" criterion (Q4_GAP), and the serving rule of ADR-036
   (RULE_POINTS, RULE_MODELS) applied level by level;
3. speed with 2 threads (results/runs/gguf-speed/, eval/gguf_speed.py);
4. per-run environment and checks, and the SHA-256 of every model file.
Every row is labelled "GGUF <quant>, CPU, not Protocol A": a different runtime, precision and machine.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from score import Scorer  # noqa: E402
from turn_cut import turn_text  # noqa: E402

RUNS = ROOT / "results" / "runs"
SPEED = RUNS / "gguf-speed"
OUT = ROOT / "eval" / "outputs"
ORDER = ["base-1.7b", "sft-1.7b-notok-s0", "sft-1.7b-tok-s0", "sft-1.7b-tok-v1.2-s0"]
TITLE = {"base-1.7b": "(a) Qwen3-1.7B-Base, no fine-tuning",
         "sft-1.7b-notok-s0": "(b) SFT rsLoRA without token rows, data v1, seed 0, merged",
         "sft-1.7b-tok-s0": "(c1) SFT rsLoRA with token rows, data v1, seed 0, merged",
         "sft-1.7b-tok-v1.2-s0": "(c) SFT rsLoRA with token rows, data v1.2, seed 0, merged"}
SHORT = {"base-1.7b": "(a)", "sft-1.7b-notok-s0": "(b)", "sft-1.7b-tok-s0": "(c1)", "sft-1.7b-tok-v1.2-s0": "(c)"}
QUANTS = ["Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
QUANT_MODELS = ["sft-1.7b-tok-s0", "sft-1.7b-tok-v1.2-s0"]  # always built at every level; the criterion is read here
# Q4_K_M is "clearly worse" when, for (c1) or (c), its Assistant /200 is at least Q4_GAP below the best of the
# higher levels of the same model: twice the seed standard deviation (3.0) of the recorded 1.7B SFT rsLoRA arm with
# token rows, 133.0 ± 3.0 (docs/limitations.md).
Q4_GAP = 6
SERVED = "Q8_0"  # ADR-036
RULE_POINTS = 3  # ADR-036: within 3 points of the recorded bf16 Assistant /200
RULE_MODELS = ["sft-1.7b-notok-s0", "sft-1.7b-tok-s0", "sft-1.7b-tok-v1.2-s0"]
STOPS = ["im_end", "endoftext", "length"]
SPEED_LABEL = "2 threads on i7-13700; an estimate for a 2-vCPU machine, not a measurement of a hosted service"


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(p: Path, rows: list[dict]) -> None:
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")


def run_name(model: str, quant: str) -> str:
    return model if quant == "Q4_K_M" else f"{model}-{quant}"


def decode() -> None:
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained("Qwen/Qwen3-1.7B-Base")
    for d in sorted(RUNS.glob("gguf-*")):
        if not (d / "generations.jsonl").exists() or (d / "answers.jsonl").exists():
            continue
        gens = jsonl(d / "generations.jsonl")
        rows, same = [], 0
        for g in gens:
            raw = tok.decode(g["gen_ids"], skip_special_tokens=False)
            same += raw == g["raw_llama"]
            rows.append({"id": g["id"], "raw": raw, "stop_reason": g["stop_reason"], "latency_ms": g["latency_ms"],
                         "n_tokens": g["n_tokens"]})
        write_jsonl(d / "answers.jsonl", rows)
        (d / "decode.json").write_text(json.dumps({"tokenizer": "Qwen/Qwen3-1.7B-Base", "skip_special_tokens": False,
                                                   "answers": len(rows), "raw_equals_llama_detokenize": same}, indent=2)
                                       + "\n", encoding="utf-8", newline="\n")
        print(d.name, len(rows), "answers;", same, "equal to llama.cpp detokenisation")


def stops(answers: list[dict]) -> str:
    c = Counter(a["stop_reason"] for a in answers)
    return " / ".join(str(c.get(k, 0)) for k in STOPS)


class Ctx:
    def __init__(self) -> None:
        self.scorer = Scorer()
        self.blocks = {it["id"]: it["block"] for it in jsonl(ROOT / "eval" / "eval_set.jsonl")}
        self.recorded: dict[str, dict] = {}

    def assistant(self, ids) -> list[str]:
        return [i for i in ids if self.blocks[i] != "R"]

    def summary(self, answers: list[dict], scores: dict[str, dict]) -> dict:
        a_ids = self.assistant(scores)
        return {"assistant": sum(scores[i]["pass"] for i in a_ids),
                "retention": sum(scores[i]["pass"] for i in scores if self.blocks[i] == "R"),
                "cut": sum(self.scorer.score(a["id"], turn_text(a["raw"]))["pass"] for a in answers
                           if self.blocks[a["id"]] != "R"),
                "stops": stops(answers)}

    def rec(self, arm: str) -> dict:
        if arm not in self.recorded:
            ans = jsonl(OUT / arm / "answers.jsonl")
            sc = {s["id"]: s for s in jsonl(OUT / arm / "scores.jsonl")}
            self.recorded[arm] = {"answers": {a["id"]: a for a in ans}, "scores": sc, **self.summary(ans, sc)}
        return self.recorded[arm]

    def gguf(self, name: str) -> dict:
        d = RUNS / f"gguf-{name}"
        run = json.loads((d / "run.json").read_text(encoding="utf-8"))
        ans = jsonl(d / "answers.jsonl")
        sc_list = [self.scorer.score(a["id"], a["raw"]) for a in ans]
        write_jsonl(d / "scores.jsonl", sc_list)
        sc = {s["id"]: s for s in sc_list}
        rec = self.rec(run["compare_arm"])
        return {"run": run, "answers": ans, "scores": sc, **self.summary(ans, sc),
                "same": sum(s["pass"] == rec["scores"][i]["pass"] for i, s in sc.items()),
                "ident": sum(a["raw"] == rec["answers"][a["id"]]["raw"] for a in ans), "recorded": rec}


def merge_text(m: dict) -> str:
    if not m:
        return "none (base weights)"
    mc = m.get("checks") or {}
    rows = ("not trained (rows equal the base)" if m.get("token_rows") is False else "trained (rows differ from the base)")
    return (f"{m.get('merge_dtype', 'bf16')} merge, saved {m.get('dtype')}; max next-token probability difference merged "
            f"vs adapter {mc.get('probs_max_abs_diff')} (limit 0.01); same top-5: {mc.get('same_top5')}; token rows: "
            f"{rows}; adapter `{m['adapter_sha256'][:16]}…`, merged manifest `{m['manifest_sha256'][:16]}…`")


def report() -> str:
    cx = Ctx()
    res = {run_name(m, q): cx.gguf(run_name(m, q)) for m in ORDER for q in QUANTS
           if (RUNS / f"gguf-{run_name(m, q)}" / "run.json").exists()}
    L = ["# Demo models: Qwen3-1.7B as GGUF on CPU",
         "",
         "`results/gguf_report.py`. **GGUF, CPU, not Protocol A.** 1.7B models converted to GGUF with llama.cpp, "
         "quantised and run with llama-cpp-python on a laptop CPU (`eval/run_gguf.py`): greedy, at most 200 new tokens, "
         "stop on `<|im_end|>` (151645) or `<|endoftext|>` (151643), batch 1, the same eval-v1 prompt ids as Protocol A "
         "(`eval/gguf_prompts.py`). Scored with `eval/score.py` (rubric v1.3). The recorded columns are the bf16 "
         "Protocol-A runs on the H200 (`eval/outputs/`); runtime, precision and hardware all differ, so the two columns "
         "are not a controlled comparison. Assistant /200 = passes on the 200 non-R items; retention /20 = the R items. "
         "Stop reasons: im_end / endoftext / length over 220. Same pass/fail = items (of 220) on which the GGUF answer "
         "and the recorded answer get the same verdict. (b) and (c1) differ only in the two trained special-token rows "
         "(same data v1, seed 0, configuration); (c) is the data-v1.2 model.",
         "",
         f"## Served files ({SERVED}, ADR-036)", "",
         f"| Model | Label | Recorded arm | File | Bytes | SHA-256 | Assistant /200 {SERVED} (recorded bf16) | "
         f"Turn-cut Assistant /200 {SERVED} (recorded bf16), diagnostic, not the official score | Retention /20 "
         f"{SERVED} (recorded bf16) | Stop reasons {SERVED} | Stop reasons recorded | Same pass/fail /220 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name in ORDER:
        r = res[run_name(name, SERVED)]
        rec, g = r["recorded"], r["run"]["gguf"]
        L.append(f"| {TITLE[name]} | {r['run']['label']} | `{r['run']['compare_arm']}` | `{g['file']}` | {g['bytes']:,} | "
                 f"`{g['sha256']}` | {r['assistant']} ({rec['assistant']}) | {r['cut']} ({rec['cut']}) | "
                 f"{r['retention']} ({rec['retention']}) | {r['stops']} | {rec['stops']} | {r['same']} |")
    L += ["", "The turn-cut column cuts each answer where the model's turn was meant to end (`eval/turn_cut.py`, as in "
              "`results/lora_no_token_rows.md`) and is never the official score. A model without trained special-token "
              "rows never emits `<|im_end|>`: it ends its turn with a neighbouring under-trained token, then invents "
              "`user` / `assistant` turns until the 200-token limit, and official scores (rubric v1.3) score the whole "
              "200 tokens. Text in the invented turns can pass rubric checks, so such a model's official score "
              "overstates it (by up to 13 points in the recorded LoRA runs, `docs/limitations.md`), and it can score "
              "higher on the official metric than a model that stops at the end of its turn."]
    L += ["", "## Other levels", "",
          "| Model | Quantisation | Label | File size (bytes) | Assistant /200 (recorded bf16) | Turn-cut Assistant /200 "
          "(recorded bf16), diagnostic, not the official score | Retention /20 (recorded bf16) | Stop reasons | "
          "Same pass/fail /220 vs recorded bf16 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for m in ORDER:
        for q in QUANTS:
            if q == SERVED or run_name(m, q) not in res:
                continue
            r = res[run_name(m, q)]
            rec = r["recorded"]
            L.append(f"| {SHORT[m]} | {q} | {r['run']['label']} | {r['run']['gguf']['bytes']:,} | {r['assistant']} "
                     f"({rec['assistant']}) | {r['cut']} ({rec['cut']}) | {r['retention']} ({rec['retention']}) | "
                     f"{r['stops']} | {r['same']} |")
    worse = {}
    for m in QUANT_MODELS:
        higher = [res[run_name(m, q)]["assistant"] for q in QUANTS[1:] if run_name(m, q) in res]
        worse[m] = bool(higher) and max(higher) - res[run_name(m, "Q4_K_M")]["assistant"] >= Q4_GAP
    levels = {m: [q for q in QUANTS if run_name(m, q) in res] for m in ORDER if m not in QUANT_MODELS}
    verdict = ("met for " + ", ".join(SHORT[m] for m in QUANT_MODELS if worse[m]) if any(worse.values()) else
               "not met for (c1) or (c)")
    verdict += "; levels run for the other models: " + "; ".join(f"{SHORT[m]} {' / '.join(v)}" for m, v in levels.items())
    L += ["", f"Q4_K_M counts as clearly worse when its Assistant /200 is at least {Q4_GAP} below the best of Q5_K_M / "
              f"Q6_K / Q8_0 of the same model ({Q4_GAP} = twice the seed standard deviation 3.0 of the recorded 1.7B "
              f"SFT rsLoRA arm with token rows, 133.0 ± 3.0, `docs/limitations.md`). Criterion: {verdict} (the base at "
              f"{SERVED} only, ADR-036)."]
    L += ["", "## Serving rule (ADR-036)", "",
          f"Rule, set before these tables were read: serve the smallest level whose Assistant /200 is within {RULE_POINTS} "
          f"points of the recorded bf16 Assistant /200 for every live fine-tuned model "
          f"({', '.join(SHORT[m] for m in RULE_MODELS)}). |GGUF − recorded| per level:", "",
          "| Level | " + " | ".join(SHORT[m] for m in RULE_MODELS) + " | Meets the rule |",
          "|---|" + "---|" * len(RULE_MODELS) + "---|"]
    meets = []
    for q in QUANTS:
        if not all(run_name(m, q) in res for m in RULE_MODELS):
            continue
        d = {m: abs(res[run_name(m, q)]["assistant"] - res[run_name(m, q)]["recorded"]["assistant"]) for m in RULE_MODELS}
        ok = all(v <= RULE_POINTS for v in d.values())
        if ok:
            meets.append(q)
        L.append(f"| {q} | " + " | ".join(str(d[m]) for m in RULE_MODELS) + f" | {'yes' if ok else 'no'} |")
    b = res[run_name(ORDER[0], SERVED)]
    base_d = abs(b["assistant"] - b["recorded"]["assistant"])
    first = meets[0] if meets else "none"
    L += ["", f"Smallest level that meets the rule: {first}"
              + (" (served)." if first == SERVED else f"; it differs from the served level {SERVED}.")
              + f" The base (a) is not part of the rule; at {SERVED} it scores {b['assistant']} against its recorded "
              f"{b['recorded']['assistant']} (difference {base_d}, {'within' if base_d <= RULE_POINTS else 'not within'} "
              f"{RULE_POINTS} points), which does not change the decision."]
    sp = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(SPEED.glob("*-t2.json"))}
    if sp:
        L += ["", "## Speed with 2 threads", "",
              f"**{SPEED_LABEL}.** `eval/gguf_speed.py`: the first {next(iter(sp.values()))['prompts']} eval-v1 prompts, "
              "one after another with one model object (the KV cache of the shared system-prompt prefix is reused, as "
              "in a single-process demo; prompt 1 starts cold). TTFT = time to first token. Decode tokens/s excludes "
              "the first token of each answer; end-to-end tokens/s includes prompt processing. Same ids = answers "
              "whose generated token ids equal the 16-thread eval run.", "",
              "| Model | Quantisation | File size (bytes) | Load (s) | TTFT cold (s) | TTFT median / p90 / max, warm (s) | "
              "Decode tokens/s | End-to-end tokens/s | Peak RAM (GB) | Same ids as 16 threads |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for m in ORDER:
            for q in QUANTS:
                s = sp.get(f"{run_name(m, q)}-t2")
                if not s:
                    continue
                L.append(f"| {SHORT[m]} | {q} | {s['gguf']['bytes']:,} | {s['load_s']} | {s['ttft_cold_s']} | "
                         f"{s['ttft_warm_median_s']} / {s['ttft_warm_p90_s']} / {s['ttft_warm_max_s']} | "
                         f"{s['decode_tokens_per_s']} | {s['end_to_end_tokens_per_s']} | {s['peak_ram_gb']} | "
                         f"{s['gen_ids_equal_16_thread_run']}/{s['prompts']} |")
    L += ["", "## Runs (16 threads)", "",
          "| Run | GGUF (demo file) | Merge | Load (s) | Tokens/s | Peak RAM (GB) | CPU, threads | Checks |",
          "|---|---|---|---|---|---|---|---|"]
    files = {}
    for name, r in res.items():
        run, ck, b = r["run"], r["run"]["checks"], r["run"]["build"]
        L.append(f"| `{name}` | `{run['gguf']['file']}` ({run['gguf']['bytes']:,} B) | {merge_text(b.get('merge') or {})} | "
                 f"{run['load_s']} | {run['tokens_per_s']} | {run['peak_ram_gb']} | {run['cpu']}, {run['threads']} | "
                 f"build checks {'passed' if b['checks_passed'] else 'FAILED'}; special tokens round-trip "
                 f"{ck['special_tokens_round_trip']}; llama.cpp tokenisation = HF ids on "
                 f"{ck['prompt_tokenisation_equal_hf']}/{ck['prompts']} prompts |")
        for fn, info in b["files"].items():
            files[fn] = info
    r0 = res[ORDER[0]]["run"]
    L += ["", "Models (b) and (c1): a first merge of their adapters in bf16 (the recorded procedure) failed "
              "`train/merge_sft.py`'s 0.01 next-token probability check and was not used; each was merged again with "
              "`--merge-dtype fp32` (float32 merge, saved in bf16) under the same, unchanged checks. Model (c) uses the "
              "recorded bf16 procedure. (b) also uses `--no-token-rows`, since its adapter has no trained special-token "
              "rows. For the merged models the converter already embeds `train/chat_template.jinja` (it is in the merged "
              "folder), so a quantised file is written directly when the f16 file carries it ((c1) and the Q5_K_M / "
              "Q6_K / Q8_0 files; (a), (b) and (c) at Q4_K_M went through the template step). The Q5_K_M / Q6_K / Q8_0 "
              "files are quantised from the f16 file of the model's Q4_K_M build (`scripts/gguf_build.py --reuse-f16`, "
              "f16 SHA-256 checked). Every demo file passes the same checks."]
    L += ["", f"llama.cpp `{r0['build']['llama_cpp_commit']}` (converter, `convert_hf_to_gguf.py`), llama-cpp-python "
              f"{r0['llama_cpp_python']} (quantisation and inference, the same llama.cpp commit vendored), project chat "
              f"template `train/chat_template.jinja` embedded (SHA-256 `{r0['build']['template_sha256'][:16]}…`); "
              "environment in `docs/compute.md`. The model files are not in the repository (kept outside git); their "
              "SHA-256:", "",
          "| File | Bytes | SHA-256 |", "|---|---|---|",
          *[f"| `{fn}` | {info['bytes']:,} | `{info['sha256']}` |" for fn, info in sorted(files.items())], ""]
    return "\n".join(L)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--decode", action="store_true")
    a = ap.parse_args()
    if a.decode:
        decode()
        return
    text = report()
    (ROOT / "results" / "gguf_demo_models.md").write_text(text, encoding="utf-8", newline="\n")
    print(text)


if __name__ == "__main__":
    main()

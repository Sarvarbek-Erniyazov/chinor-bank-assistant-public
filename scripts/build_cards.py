"""Model cards (model_cards/*.md) and data cards (data/cards/*.md), from committed files only.

python scripts/build_cards.py          (after scripts/method_table.py; part of scripts/regen_outputs.py)

Every card states the fiction notice, the four limits of the evaluation (verbatim from docs/limitations.md and the
README fiction notice; the build stops if a quote is no longer in its source), intended use, licences with the
Banking77 citation (data/DATA_SOURCES.md) and "upload pending" (nothing is on the Hugging Face Hub). Model cards add
the base model with its pinned revision (docs/base_revisions.md), the training data version with its manifest
SHA-256, the adapter / weights SHA-256 (results/adapter_sha256.tsv, results/model_sha256.tsv, results/gguf_demo_models.md),
the training settings (results/runs/<arm>/train/run.json) and the scores with their source file, computed with the
functions of scripts/method_table.py.
The hashed DATA_CARD.md files inside data/sft/<version>/ belong to each version's manifest.sha256 and are not
changed; data/cards/ holds the cards with the common fields and links to them.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "model_cards"
DATA_DIR = ROOT / "data" / "cards"
RUNS = ROOT / "results" / "runs"
UPLOAD = "**Upload pending.** Not on the Hugging Face Hub: no Hub repository exists yet."


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MT = _load("method_table", ROOT / "scripts" / "method_table.py")


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def norm(s: str) -> str:
    s = re.sub(r"(?m)^>\s?", "", s)
    return re.sub(r"\s+", " ", s).strip()


def quote(rel: str, text: str) -> str:
    """text, after checking that it appears verbatim (up to line wrapping) in the source file."""
    if norm(text) not in norm(read(rel)):
        raise SystemExit(f"quote no longer in {rel}: {text[:80]}…")
    return text


LIMITS = [
    ("Canonical-answer eval", "docs/limitations.md",
     "SFT v1 teaches one fixed answer per intent, so the eval measures recall on T-seen, not generalisation from the "
     "handbook."),
    ("Lenient scorer", "docs/limitations.md",
     "51/60 = 0.85 [0.74, 0.92] agreement with one annotator; errors lenient (8 of 9): automatic Assistant scores are "
     "upper bounds (audit-corrected 14B v1.2: about 121–126 /200 vs 142–148 auto, exploratory, one 60-item audit)."),
    ("One annotator", "docs/limitations.md",
     "Independent human inter-annotator agreement: not measured; all hand labels by one annotator (intra-rater "
     "re-marking not done). The annotator (the project author) also wrote the eval and red-team sets and the handbook."),
    ("Fictional bank", "data/DATA_SOURCES.md",
     "Chinor Bank does not exist. Every policy, fee, limit, phone number, code and timing in this repository was "
     "invented for the project and deliberately differs from common industry defaults. Nothing here describes, "
     "imitates or is affiliated with any real bank."),
]
QWEN_CITE = ("Qwen3 models (0.6B–14B base and instruct; Qwen3-32B as the rewrite generator), Apache-2.0: Qwen Team "
             "(2025), *Qwen3 Technical Report*, arXiv:2505.09388.")


def fiction() -> str:
    return "> **Fiction notice.** " + quote("data/DATA_SOURCES.md", LIMITS[3][2])


def limits_md() -> list[str]:
    out = ["## Limits", ""]
    for label, src, text in LIMITS:
        out.append(f"- **{label}:** {quote(src, text)} (`{src}`)")
    return out + ["", "Every limit with its measurement: `docs/limitations.md`.", ""]


def banking77_bibtex() -> str:
    m = re.search(r"```\n(\s*@inproceedings\{Casanueva2020.*?)\n\s*```", read("data/DATA_SOURCES.md"), re.S)
    return textwrap.dedent(m.group(1)).rstrip()


def licences_md(uses_banking77: bool = True) -> list[str]:
    out = ["## Licences", "",
           f"- Base model: {quote('data/DATA_SOURCES.md', QWEN_CITE)}",
           "- Project data (handbook, hand-written items, eval sets, SFT and preference data): CC BY 4.0 "
           "(`LICENSE-DATA`); code: Apache-2.0 (`LICENSE`)."]
    if uses_banking77:
        out += ["- Banking77 customer queries (the user turns of the SFT data), CC BY 4.0 (`data/DATA_SOURCES.md`):", "",
                "```", banking77_bibtex(), "```"]
    return out + [""]


def intended_use(kind: str) -> list[str]:
    return ["## Intended use", "",
            f"Research and demonstration of this closed pilot study only: reading the recorded answers, reproducing the "
            f"tables, and the live side-by-side demo. Not for answering questions about any real bank, not for real "
            f"customers, and not as evidence of general banking competence. {kind}", ""]


def revisions() -> dict:
    out = {}
    for line in read("docs/base_revisions.md").splitlines():
        c = [x.strip().strip("`") for x in line.strip("|").split("|")]
        if len(c) > 3 and c[0].startswith("Qwen/"):
            out[c[0]] = c[2]
    return out


def sha_tables() -> dict:
    out = {}
    with (ROOT / "results" / "adapter_sha256.tsv").open(encoding="utf-8") as f:
        for r in csv.reader(f, delimiter="\t"):
            if r and r[0] != "run":
                out[r[0]] = (r[1], "adapter_model.safetensors", "results/adapter_sha256.tsv")
    with (ROOT / "results" / "model_sha256.tsv").open(encoding="utf-8") as f:
        for r in csv.reader(f, delimiter="\t"):
            if r:
                out[r[0]] = (r[2], r[1], "results/model_sha256.tsv")
    return out


def manifest(data_dir: str) -> dict:
    p = ROOT / data_dir / "manifest.sha256"
    if not p.exists():
        return {}
    return {l.split()[1]: l.split()[0] for l in p.read_text(encoding="utf-8").splitlines() if l.strip()}


def train_run(arm: str) -> dict:
    return json.loads((RUNS / arm / "train" / "run.json").read_text(encoding="utf-8"))


def settings(cv: dict) -> str:
    lo = cv.get("lora", {})
    parts = [f"{'rsLoRA' if lo.get('use_rslora') else 'LoRA'} r {lo.get('r')}, α {lo.get('alpha')}"]
    if lo.get("trainable_token_rows"):
        parts.append(f"trained token rows {', '.join(map(str, lo['trainable_token_rows']))}")
    if cv.get("loss"):
        parts.append(f"loss {cv['loss']}" + "".join(f", {k} {cv[k]}" for k in ("beta", "gamma") if k in cv))
    parts.append(f"lr {cv['learning_rate']:g}, {cv['num_train_epochs']} epochs, max length {cv['max_length']}")
    return "; ".join(parts)


class Scores:
    def __init__(self):
        self.passes, self.block = MT.load_items()
        self.items = sorted(i for i, b in self.block.items() if b in MT.ASSISTANT)
        self.r_items = sorted(i for i, b in self.block.items() if b == "R")

    def assistant(self, arms):
        return MT.mean_sd(MT.vectors(self.passes, arms, self.items))

    def retention(self, arms):
        return MT.mean_sd(MT.vectors(self.passes, arms, self.r_items))

    def delta(self, arms, comp):
        return MT.delta(MT.vectors(self.passes, arms, self.items), MT.vectors(self.passes, comp, self.items))


ADAPTER_CARDS = [
    # (arm, title, group arms, comparison arms, comparison label, family / extra source)
    ("l14b_sft_rslora_tok-s0-v1.2", "Qwen3-14B-Base SFT (rsLoRA with token rows, data v1.2, seed 0)",
     [f"l14b_sft_rslora_tok-s{i}-v1.2" for i in range(5)], MT.BASE14, "Qwen3-14B-Base 0-shot",
     "This seed is the one SFT parent of all six DPO / SimPO runs."),
    ("pref_dpo_rules-s0", "DPO on 14B SFT (rule pairs, seed 0)", [f"pref_dpo_rules-s{i}" for i in range(3)],
     MT.SFT_V12_S0, "its one SFT parent, 14B v1.2 seed 0",
     "Load on top of sft-merged (the SFT v1.2 seed 0 adapter merged into the base), not on the raw base."),
    ("pref_simpo_rules-s0", "SimPO on 14B SFT (rule pairs, seed 0)", [f"pref_simpo_rules-s{i}" for i in range(3)],
     MT.SFT_V12_S0, "its one SFT parent, 14B v1.2 seed 0",
     "Load on top of sft-merged (the SFT v1.2 seed 0 adapter merged into the base), not on the raw base."),
]


def adapter_card(sc: Scores, revs: dict, shas: dict, arm, title, group, comp, comp_label, note) -> str:
    tr = train_run(arm)
    cv = tr["config_values"]
    pref = "pairs" in tr
    base = "Qwen/Qwen3-14B-Base"
    sha, fname, sha_src = shas[arm]
    if pref:
        data = (f"`{tr['pairs']}` (SHA-256 `{tr['pairs_sha256']}`, {tr['pairs_used']} pairs), on top of sft-merged "
                f"(manifest SHA-256 `{tr['sft_merged_manifest_sha256']}`, `docs/compute.md`)")
    else:
        man = manifest(tr["data_dir"])
        data = f"`{tr['data_dir']}` (train.jsonl SHA-256 `{man['train.jsonl']}`, `{tr['data_dir']}/manifest.sha256`)"
    rt1, rtg = MT.redteam([arm]), MT.redteam(group)
    L = ["---", "license: apache-2.0", f"base_model: {base}", "library_name: peft",
         f"tags: [lora, rslora, {cv.get('loss', 'sft')}, customer-support, fictional-bank]", "---", "",
         f"# Chinor assistant: {title}", "", fiction(), "",
         UPLOAD + " The adapter is not in git; " + (
             f"`scripts/verify_adapters.py` checks a copy against `{sha_src}`." if sha_src.endswith("adapter_sha256.tsv")
             else f"its SHA-256 is recorded in `{sha_src}`."), "",
         "## Identity", "",
         "| Field | Value |", "|---|---|",
         f"| Run | `{arm}` (`results/runs/{arm}/train/run.json`) |",
         f"| Base model | `{base}`, revision `{revs[base]}` (`docs/base_revisions.md`) |",
         f"| Training data | {data} |",
         f"| Configuration | `{tr['config']}`, seed {tr['seed']}: {settings(cv)} |",
         f"| `{fname}` SHA-256 | `{sha}` (`{sha_src}`) |",
         "| Prompt format | system prompt `handbook/system_prompt.txt`, template `train/chat_template.jinja`, greedy, "
         "stop on `<\\|im_end\\|>` (151645) or `<\\|endoftext\\|>` (151643) |", "",
         note, "",
         "## Scores", "",
         "Eval-v1 (frozen), Protocol A (H200, bf16, greedy), rubric v1.3. Computed by `scripts/build_cards.py` with the "
         "functions of `scripts/method_table.py` from `results/tidy/items_long.csv` and "
         "`eval/outputs/rt-<run>/redteam_scores.jsonl`.", "",
         "| Measure | This seed | All seeds of the arm | Source |", "|---|---|---|---|",
         f"| Assistant /{len(sc.items)} | {sc.assistant([arm])} | {sc.assistant(group)} ({len(group)} seeds) | "
         "`results/method_table.md`, `results/tidy/arm_summary.csv` |",
         f"| Retention /{len(sc.r_items)} (no system prompt) | {sc.retention([arm])} | {sc.retention(group)} | "
         "`results/tidy/arm_summary.csv` |",
         f"| Δ Assistant vs {comp_label} [95 % CI] | — | {sc.delta(group, comp)} | `results/method_table.md` |",
         f"| Red-team attack success (lower is better) | {rt1} | {rtg} | `results/redteam.md` |", ""]
    L += intended_use("Use it with the frozen system prompt and template above; other prompts were not evaluated.")
    L += limits_md() + licences_md()
    return "\n".join(L) + "\n"


def gguf_rows() -> tuple[dict, dict]:
    text = read("results/gguf_demo_models.md")
    served, runs = {}, {}
    for line in text.split("## Other levels")[0].splitlines():
        if line.startswith("| ("):
            c = [x.strip() for x in line.strip().strip("|").split(" | ")]
            served[c[3].strip("`")] = c
    for line in text.split("## Runs (16 threads)")[1].splitlines():
        if line.startswith("| `"):
            c = [x.strip() for x in line.strip().strip("|").split(" | ")]
            runs[c[0].strip("`")] = c
    return served, runs


def gguf_card(sc: Scores, revs: dict, shas: dict, label: str, name: str) -> str:
    served, runs = gguf_rows()
    q = MT.GGUF_QUANT
    fname = f"{name}-{q}.gguf"
    s, r = served[fname], runs[f"{name}-{q}"]
    run = json.loads((RUNS / f"gguf-{name}-{q}" / "run.json").read_text(encoding="utf-8"))
    rec = run["compare_arm"]
    base = "Qwen/Qwen3-1.7B-Base"
    trained = (RUNS / rec / "train" / "run.json").exists()
    L = ["---", "license: apache-2.0", f"base_model: {base}", "library_name: gguf",
         "tags: [gguf, llama.cpp, customer-support, fictional-bank]", "---", "",
         f"# Chinor demo model {label}, GGUF {q}", "", fiction(), "",
         UPLOAD + " The file is not in git (kept outside the repository); its SHA-256 is below.", "",
         f"**GGUF {q} on CPU, not the evaluation protocol.** The live demo (`space/`) serves this file (ADR-036).", "",
         "## Identity", "", "| Field | Value |", "|---|---|",
         f"| File | `{fname}`, {s[4]} bytes, SHA-256 `{s[5].strip('`')}` (`results/gguf_demo_models.md`) |",
         f"| Base model | `{base}`, revision `{revs[base]}` (`docs/base_revisions.md`) |"]
    if trained:
        tr = train_run(rec)
        man = manifest(tr["data_dir"])
        sha, fn, src = shas[rec]
        L += [f"| Training data | `{tr['data_dir']}` (train.jsonl SHA-256 `{man['train.jsonl']}`, "
              f"`{tr['data_dir']}/manifest.sha256`) |",
              f"| Training run | `{rec}`: `{tr['config']}`, seed {tr['seed']}: {settings(tr['config_values'])} |",
              f"| Adapter `{fn}` SHA-256 | `{sha}` (`{src}`) |",
              f"| Merge | {r[2]} (`results/gguf_demo_models.md`) |"]
    else:
        L += ["| Training data | none: the base weights, no fine-tuning |"]
    L += [f"| Conversion | {run['label']}; llama-cpp-python {run['llama_cpp_python']}; template "
          "`train/chat_template.jinja` embedded; details in `results/gguf_demo_models.md` and `docs/compute.md` |", "",
          "## Scores", "",
          f"Eval-v1 on a laptop CPU with llama-cpp-python (`eval/run_gguf.py`), greedy, the Protocol-A prompt ids; "
          f"scored with rubric v1.3. The recorded column is the bf16 Protocol-A run `{rec}`: runtime, precision and "
          "machine all differ. Red-team: not run on this file.", "",
          "| Measure | GGUF (recorded bf16) | Source |", "|---|---|---|",
          f"| Assistant /{len(sc.items)} | {s[6]} | `results/gguf_demo_models.md` |",
          f"| Turn-cut Assistant /{len(sc.items)}, diagnostic, not the official score | {s[7]} | "
          "`results/gguf_demo_models.md` |",
          f"| Retention /{len(sc.r_items)} | {s[8]} | `results/gguf_demo_models.md` |",
          f"| Stop reasons (im_end / endoftext / length) | {s[9]} ({s[10]}) | `results/gguf_demo_models.md` |",
          f"| Same pass/fail as the recorded run | {s[11]} | `results/gguf_demo_models.md` |",
          f"| Δ Assistant vs the recorded run [95 % CI] | "
          f"{MT.delta([[int(x['pass']) for x in sorted(MT.jsonl(RUNS / f'gguf-{name}-{q}' / 'scores.jsonl'), key=lambda x: x['id']) if x['id'] in set(sc.items)]], MT.vectors(sc.passes, [rec], sc.items))} | "
          "`results/method_table.md` |", ""]
    L += intended_use("Served in the live demo next to another model to show what training changed, including the "
                      "end-of-turn behaviour.")
    L += limits_md() + licences_md(uses_banking77=trained)
    return "\n".join(L) + "\n"


DATA_CARDS = [
    # (card name, data dir, built by, what it is)
    ("sft-v1", "data/sft/v1", "data/build_sft.py",
     "SFT data v1: Banking77 customer queries with canonical answers from the fictional handbook, plus hand-written "
     "behaviour examples (ADR-024)."),
    ("sft-v1.1", "data/sft/v1.1", "data/build_v1_1.py", "SFT data v1.1: v1 with more asking turns (ADR-028)."),
    ("sft-v1.2", "data/sft/v1.2", "data/build_v1_2.py", "SFT data v1.2: v1.1 plus hand-written handoff examples (ADR-029)."),
    ("sft-v1.2_rft", "data/sft/v1.2_rft", "data/sft/build_rft.py",
     "RFT data: v1.2 plus verified on-policy samples of the SFT model (exploratory, ADR-033)."),
    ("pref-v1", "data/pref/v1", "data/pref/label_rules.py",
     "Preference data v1: rule-labelled pairs of on-policy samples of sft-merged (14B SFT v1.2 seed 0)."),
]


UNHASHED_FILES = {"data/pref/v1": ["prompts.jsonl", "pairs_rules.jsonl", "pairs_v2.jsonl"]}


def lines(p: Path) -> int:
    return sum(1 for l in p.read_text(encoding="utf-8").splitlines() if l.strip())


def trained_on(data_dir: str) -> list[str]:
    out = []
    for p in sorted(RUNS.glob("*/train/run.json")):
        tr = json.loads(p.read_text(encoding="utf-8"))
        if tr.get("data_dir") == data_dir or (tr.get("pairs") or "").startswith(data_dir + "/"):
            out.append(p.parent.parent.name)
    return out


def data_card(name, data_dir, built_by, what) -> str:
    d = ROOT / data_dir
    man = manifest(data_dir)
    # no manifest (pref v1): the tracked files only (labels.jsonl is git-ignored, so it is not part of the release)
    files = sorted(man) if man else UNHASHED_FILES[data_dir]
    rows = [f"| `{f}` | {lines(d / f) if f.endswith('.jsonl') else '—'} | "
            f"`{man.get(f) or hashlib.sha256((d / f).read_bytes()).hexdigest()}` |" for f in files]
    arms = trained_on(data_dir)
    L = [f"# Data card: {name}", "", fiction(), "", UPLOAD, "", what, "",
         "| Field | Value |", "|---|---|",
         f"| Folder | `{data_dir}/` |", f"| Built by | `{built_by}` |",
         f"| Detailed card | `{data_dir}/DATA_CARD.md` (written by the builder" +
         (", hashed in `manifest.sha256`, unchanged)" if man else ", unchanged)") + " |",
         f"| Runs trained on it | {', '.join(f'`{a}`' for a in arms) or 'none recorded'} |", "",
         "| File | Records | SHA-256 |", "|---|---|---|", *rows,
         "", "SHA-256 from `manifest.sha256` where the folder has one, else computed from the file.", ""]
    L += intended_use("Training data for the study's adapters; do not use it to train or test anything about a real "
                      "bank. The eval sets are separate and carry a canary (`eval/FROZEN.md`): do not train on them.")
    L += limits_md() + licences_md()
    return "\n".join(L) + "\n"


def build() -> dict[Path, str]:
    sc, revs, shas = Scores(), revisions(), sha_tables()
    out = {}
    for arm, title, group, comp, comp_label, note in ADAPTER_CARDS:
        out[MODEL_DIR / f"{arm}.md"] = adapter_card(sc, revs, shas, arm, title, group, comp, comp_label, note)
    for label, name in MT.GGUF:
        out[MODEL_DIR / f"gguf-{name}-{MT.GGUF_QUANT}.md"] = gguf_card(sc, revs, shas, label, name)
    for card in DATA_CARDS:
        out[DATA_DIR / f"{card[0]}.md"] = data_card(*card)
    return out


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for p, text in build().items():
        p.write_text(text, encoding="utf-8", newline="\n")
        print("wrote", p.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()

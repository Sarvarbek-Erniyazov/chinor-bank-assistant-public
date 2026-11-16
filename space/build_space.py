"""Build the data of the live demo (space/) from committed files only. CPU, no network, no model files.

python space/build_space.py
Writes:
- space/data/assets.json: the four models (label, GGUF file name, bytes, SHA-256 and their scores, parsed from the
  "Served files" table of results/gguf_demo_models.md: Assistant /200, turn-cut diagnostic and retention, each GGUF
  and recorded bf16; stop reasons; same pass/fail); the examples (the pre-registered items of
  results/qualitative_ids.json, with their Protocol-A messages as eval/run_eval.py builds them, no few-shot turns);
  the notice (the viewer's source-checked quotes, demo/build_viewer.py BANNER, plus the protocol sentence); the
  numbers of handbook/handbook.md (eval/score.py numbers_in) for the rule flags; links.
- space/vendor/: byte copies of eval/score.py, eval/turn_cut.py, handbook/system_prompt.txt and
  train/chat_template.jinja, so space/ runs without the rest of the repository.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPACE = ROOT / "space"
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "demo"))
from build_viewer import BANNER, check_banner  # noqa: E402
from score import numbers_in  # noqa: E402

REPORT = ROOT / "results" / "gguf_demo_models.md"
SERVED = "Q8_0"
PROTOCOL = "GGUF Q8_0 on CPU, not the evaluation protocol"
# Order and labels shown in the app; key -> GGUF name stem (results/gguf_report.py ORDER), full label (scores table
# and answer headings), short label (model dropdowns: fits a 390 px phone screen).
MODELS = [
    ("base", "base-1.7b", "Base: Qwen3-1.7B-Base, no fine-tuning", "Base"),
    ("b", "sft-1.7b-notok-s0", "SFT without token rows (b)", "SFT, no end-token fix"),
    ("c1", "sft-1.7b-tok-s0", "SFT with token rows (c1), same data and seed as (b)", "SFT, end-token fix"),
    ("c", "sft-1.7b-tok-v1.2-s0", "SFT v1.2 (c), with token rows", "SFT, data v1.2"),
]
DEFAULT_PAIR = ["b", "c1"]
VENDOR = {"score.py": "eval/score.py", "turn_cut.py": "eval/turn_cut.py",
          "system_prompt.txt": "handbook/system_prompt.txt", "chat_template.jinja": "train/chat_template.jinja"}
LINKS = {"repository": "https://github.com/Sarvarbek-Erniyazov/chinor-bank-assistant-public",
         "viewer": "https://sarvarbek-erniyazov.github.io/chinor-bank-assistant-public/demo/viewer/index.html"}
PAIR = re.compile(r"^(\d+) \((\d+)\)$")


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def served_rows() -> dict[str, dict]:
    """Rows of the "## Served files (Q8_0, ...)" table of results/gguf_demo_models.md, keyed by GGUF name stem."""
    lines = REPORT.read_text(encoding="utf-8").splitlines()
    i = next(k for k, l in enumerate(lines) if l.startswith(f"## Served files ({SERVED}"))
    head = next(k for k in range(i, len(lines)) if lines[k].startswith("| Model |"))
    cols = [c.strip() for c in lines[head].strip("|").split("|")]
    out = {}
    for l in lines[head + 2:]:
        if not l.startswith("|"):
            break
        cells = dict(zip(cols, (c.strip() for c in l.strip("|").split("|"))))

        def pair(prefix):
            v = next(cells[c] for c in cols if c.startswith(prefix))
            g, r = PAIR.match(v).groups()
            return {"gguf": int(g), "recorded": int(r)}
        file = cells["File"].strip("`")
        assert file.endswith(f"-{SERVED}.gguf"), file
        out[file[:-len(f"-{SERVED}.gguf")]] = {
            "file": file, "bytes": int(cells["Bytes"].replace(",", "")), "sha256": cells["SHA-256"].strip("`"),
            "label_protocol": cells["Label"], "recorded_arm": cells["Recorded arm"].strip("`"),
            "assistant": pair("Assistant /200"), "turn_cut": pair("Turn-cut"), "retention": pair("Retention"),
            "stops_gguf": next(cells[c] for c in cols if c.startswith(f"Stop reasons {SERVED}")),
            "stops_recorded": cells["Stop reasons recorded"], "same_pass_fail": int(cells["Same pass/fail /220"])}
    return out


def examples() -> list[dict]:
    from run_eval import SYSTEM_PROMPT, build_messages
    system_prompt = SYSTEM_PROMPT.read_text(encoding="utf-8").strip()
    items = {it["id"]: it for it in jsonl(ROOT / "eval" / "eval_set.jsonl")}
    chosen = json.loads((ROOT / "results" / "qualitative_ids.json").read_text(encoding="utf-8"))["chosen"]
    out = []
    for block, iid in chosen.items():
        it = items[iid]
        out.append({"id": iid, "block": it["block"], "question": it["messages"][-1]["content"],
                    "messages": build_messages(it, system_prompt, [])})
    return out


def build() -> dict:
    check_banner()
    rows = served_rows()
    models = []
    for key, stem, label, short in MODELS:
        models.append({"key": key, "stem": stem, "label": label, "short": short, **rows[stem]})
    assets = {
        "source": "space/build_space.py from results/gguf_demo_models.md, results/qualitative_ids.json, "
                  "eval/eval_set.jsonl, demo/build_viewer.py BANNER, handbook/handbook.md",
        "served_level": SERVED, "protocol_notice": PROTOCOL, "flag_label": "automatic rule check, lenient",
        "models": models, "default_pair": DEFAULT_PAIR,
        "examples": examples(),
        "notice": [{"label": l, "source": s, "text": t} for l, s, t in BANNER],
        "handbook_numbers": sorted(numbers_in((ROOT / "handbook" / "handbook.md").read_text(encoding="utf-8"))),
        "links": LINKS,
    }
    (SPACE / "data").mkdir(parents=True, exist_ok=True)
    (SPACE / "data" / "assets.json").write_text(json.dumps(assets, indent=1, ensure_ascii=False) + "\n",
                                                encoding="utf-8", newline="\n")
    (SPACE / "vendor").mkdir(parents=True, exist_ok=True)
    for dst, src in VENDOR.items():
        shutil.copyfile(ROOT / src, SPACE / "vendor" / dst)
    return assets


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    a = build()
    print(f"space/data/assets.json: {len(a['models'])} models, {len(a['examples'])} examples, "
          f"{len(a['notice'])} notice quotes; space/vendor/: {len(VENDOR)} files")


if __name__ == "__main__":
    main()

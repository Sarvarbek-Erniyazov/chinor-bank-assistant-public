"""README.md from README.template.md and committed result files.

python scripts/build_readme.py            write README.md
python scripts/build_readme.py --check    exit 1 if README.md differs from a fresh build (no writing)

The template holds the prose and the structure and no number. Three placeholder kinds are filled here:
  {{v:name}}               a value computed by values() from a committed result file;
  {{b:name}}               a generated multi-line block (tables, code, citations), also from values();
  {{q:path|start}}         a quotation: the sentence of <path> that begins with <start>, copied verbatim
  {{q:path|start|end}}     (whitespace joined), or the text from <start> through <end>. <start> and <end> hold no
                           digit, so the template stays free of numbers; the build stops if a quote is not found.
build() also returns the character spans of every filled placeholder and the (text, file) pairs that
tests/test_readme.py checks: every digit outside a span must match ALLOWED, every quote must occur in its source,
and every value that also appears in results/method_table.md, figures/T1.md, results/redteam.md or
results/gguf_demo_models.md must equal it there.
Inputs: results/method_table.md rows (scripts/method_table.py table()), results/tidy/{arm_summary,items_long,
stop_reasons,trust}.csv, results/rewrite_funnel.json, results/lora_vs_qlora.md, results/lora_no_token_rows.md,
results/gguf_demo_models.md, figures/T1.md, results/preference.md, space/config.json, CITATION.cff,
data/DATA_SOURCES.md, docs/limitations.md.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "README.template.md"
TARGET = ROOT / "README.md"
PLACEHOLDER = re.compile(r"\{\{(?P<kind>[vbq]):(?P<arg>.*?)\}\}", re.S)
REPO = "https://github.com/Sarvarbek-Erniyazov/chinor-bank-assistant-public"
PAGES = "https://sarvarbek-erniyazov.github.io/chinor-bank-assistant-public"
# Digits allowed outside generated spans (tests/test_readme.py; listed in the README build report).
ALLOWED = [
    ("model sizes", r"\b\d+(?:\.\d+)?B\b"),
    ("model and dataset names", r"Qwen3|Banking77|Q8_0|Gemma-4"),
    ("licence names", r"CC BY 4\.0|Apache-2\.0|SHA-256"),
    ("years and dates", r"\b20\d\d(?:-\d\d-\d\d)?\b"),
    ("version tags", r"\bv\d+(?:\.\d+)*\b|\beval-v1\b|\bredteam-v1\b|\bcff-version\b"),
    ("ADR numbers", r"\bADR-\d+\b"),
    ("figure and table ids", r"(?i)\b[FT]\d+[a-f]?\b"),
    ("image display widths", r'\bwidth="\d+"'),
    ("hardware names", r"\bH200\b|\bT4\b"),
    ("eval block names", r"\bB[1-4]\b"),
    ("file names and paths", r"[\w.*<>-]*(?:/[\w.*<>-]*)+/?|[\w*-]+\.(?:md|py|txt|csv|json|jsonl|cff|png|gguf|sh|ipynb)\b"),
]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MT = _load("method_table", ROOT / "scripts" / "method_table.py")
S = MT.S


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def csv_rows(rel: str) -> list[dict]:
    with (ROOT / rel).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def md_rows(rel: str, section: str | None = None) -> list[list[str]]:
    """Table rows of a generated markdown file (escaped pipes kept inside cells), optionally of one ## section."""
    text = read(rel)
    if section:
        text = text.split(f"## {section}", 1)[1].split("\n## ", 1)[0]
    out = []
    for line in text.splitlines():
        if line.startswith("| ") and not line.startswith("|---"):
            line = line.replace("<|im_end|>", "\0")  # unescaped in some headers
            out.append([c.strip().replace("\\|", "|").replace("\0", "<|im_end|>")
                        for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]])
    return out


def norm(s: str) -> str:
    """Blockquote markers dropped and whitespace joined, so a sentence wrapped over lines reads as one."""
    return re.sub(r"\s+", " ", re.sub(r"(?m)^>\s?", "", s)).strip()


def quote(path: str, start: str, end: str | None = None) -> str:
    """The sentence of path beginning with start (to the first '.' followed by a space or the end), or start..end."""
    text = norm(read(path))
    i = text.find(start)
    if i < 0:
        raise SystemExit(f"quote not found in {path}: {start!r}")
    if end:
        j = text.find(end, i)
        if j < 0:
            raise SystemExit(f"quote end not found in {path}: {end!r}")
        return text[i:j + len(end)]
    m = re.compile(r"\.(?=\s|$)").search(text, i)
    return text[i:m.end()]


def link_paths(cell: str) -> str:
    """`path` → [path](path) for repository paths in a method-table source cell."""
    return re.sub(r"`([^`]+)`", lambda m: f"[{m.group(1)}]({m.group(1)})", cell)


def values() -> tuple[dict, list[tuple[str, str]]]:
    V: dict[str, str] = {}
    checks: list[tuple[str, str]] = []  # (text, file): the text must occur in the file

    def put(name: str, text, *files: str) -> None:
        V[name] = str(text)
        checks.extend((str(text), f) for f in files)

    T = MT.table()
    rows = {r["method"]: r for r in T["rows"]}

    def row(prefix: str) -> dict:
        return next(r for k, r in rows.items() if k.startswith(prefix))

    na = T["n_assistant"]
    put("n_items", T["n_items"])
    put("n_attacks", MT.N_ATTACKS)
    put("n_assistant", na)
    put("ci_level", "95 %")  # the level of every interval in figures/stats.py (z = 1.959964, alpha = 0.05)
    put("pages_viewer", f"{PAGES}/demo/viewer/index.html")
    put("tag_b", MT.GGUF[1][0].split()[0])
    put("tag_c1", MT.GGUF[2][0].split()[0])

    # F16 caption: means from the method table, pooled Wilson rates from arm_summary.csv (format of T1)
    summ = {r["arm_group"]: r for r in csv_rows("results/tidy/arm_summary.csv")}
    for key, group, prefix in [("base", "base-14B-0shot-A", "Base, Qwen3-14B"),
                               ("instr", "ref-14B-instruct-A", "Instruct reference"),
                               ("sft", "l14b_sft_rslora_tok-v1.2", "SFT rsLoRA with token rows, data v1.2")]:
        s = summ[group]
        rate = (f"{100 * float(s['assistant_rate']):.1f} % [{100 * float(s['assistant_ci_lo']):.1f}, "
                f"{100 * float(s['assistant_ci_hi']):.1f}]")
        put(f"f16_{key}_mean", row(prefix)["mean"], "results/method_table.md")
        put(f"f16_{key}_rate", rate, *(["figures/T1.md"] if key != "sft" else []))
        put(f"f16_{key}_seeds", s["seeds"])
    put("f16_alt", f"Assistant items passed of {na}: Qwen3-14B-Base 0-shot {V['f16_base_mean']}, Qwen3-14B Instruct "
                   f"{V['f16_instr_mean']}, SFT rsLoRA v1.2 {V['f16_sft_mean']} over {V['f16_sft_seeds']} seeds; bars are "
                   "Wilson 95 % intervals and small dots single seeds")

    # read-this-first: scorer audit (trust.csv)
    trust = csv_rows("results/tidy/trust.csv")
    aud = next(r for r in trust if r["check"].startswith("scorer pass/fail agreement") and "14B" in r["check"])
    put("scorer_k_n", f"{aud['k']}/{aud['n']}", "docs/limitations.md")
    lenient = re.search(r"(\d+) of (\d+) errors lenient", aud["note"])
    put("scorer_lenient", f"{lenient.group(1)} of {lenient.group(2)}", "docs/limitations.md")
    corr = [float(re.search(r"corrected (\d+\.\d)", r["note"]).group(1)) for r in trust
            if r["check"].startswith("audit-corrected Assistant")]
    put("corrected_range", f"{round(min(corr))}–{round(max(corr))}", "docs/limitations.md")
    batch = next(r for r in trust if r["check"].startswith("eval batch"))
    put("batch_a", batch["k"], "figures/T1.md")
    put("batch_b", batch["n"], "docs/limitations.md")

    # method table (README columns)
    cols = ["method", "question", "seeds", "mean", "delta", "comp", "holm", "vram", "status", "source"]
    head = dict(T["head"], question="Question it answers")
    L = ["| " + " | ".join(head[c] for c in cols) + " |", "|" + "---|" * len(cols)]
    for r in T["rows"]:
        cells = [link_paths(r[c]) if c == "source" else r[c] for c in cols]
        L.append("| " + " | ".join(cells) + " |")
        for c in ("mean", "delta", "vram"):
            if r[c] != "—":
                checks.append((r[c], "results/method_table.md"))
    for i, note in enumerate(T["notes"]):
        L += ["", f"{MT.SUPERSCRIPT[i]} Δ {note}."]
    V["method_table"] = "\n".join(L)
    put("boot_n", f"{S.BOOT_N:,}")

    # finding: the end-of-turn token
    stops = csv_rows("results/tidy/stop_reasons.csv")

    def stop_count(group: str, reason: str | None = None) -> int:
        return sum(int(r["count"]) for r in stops if r["arm_group"] == group and (reason is None or r["stop_reason"] == reason))
    for key, group in [("notok", "l14b_sft_rslora"), ("tok", "l14b_sft_rslora_tok")]:
        put(f"eot_{key}_imend", stop_count(group, "im_end"))
        put(f"eot_{key}_length", stop_count(group, "length"))
        put(f"eot_{key}_n", stop_count(group))
    served = {r[0][:4].strip(): r for r in md_rows("results/gguf_demo_models.md", "Served files (Q8_0, ADR-036)")[1:]}
    for key, tag in [("b", "(b)"), ("c1", "(c1)")]:
        r = next(v for k, v in served.items() if k.startswith(tag))
        put(f"gguf_{key}_stops", r[9], "results/gguf_demo_models.md")
        put(f"gguf_{key}_official", r[6].split(" (")[0], "results/gguf_demo_models.md")
        put(f"gguf_{key}_cut", r[7].split(" (")[0], "results/gguf_demo_models.md")
    nt = next(r for r in md_rows("results/lora_no_token_rows.md") if r[0].startswith("14B rsLoRA"))
    put("nt14_official", nt[2], "results/lora_no_token_rows.md")
    put("nt14_cut", nt[3], "results/lora_no_token_rows.md")
    put("nt14_fixed", nt[5], "results/lora_no_token_rows.md")

    # what did not work (F15 panels)
    fun = json.loads(read("results/rewrite_funnel.json"))
    a1, a2 = fun["audits"]
    for key, a in [("rw1", a1), ("rw2", a2)]:
        put(f"{key}_kn", f"{a['k_unsupported']}/{a['n']}")
        p, lo, hi = S.wilson(a["k_unsupported"], a["n"])
        put(f"{key}_ci", f"{100 * p:.1f} % [{100 * lo:.1f}, {100 * hi:.1f}]")
    put("rw_target", f"{100 * fun['target_rate']:.0f} %")
    put("dv11_delta", row("SFT data v1.1")["delta"], "results/method_table.md", "results/arm_differences.md")
    put("dv12_delta", row("SFT data v1.2 (handoff")["delta"], "results/method_table.md", "results/arm_differences.md")
    put("dpo_delta", row("DPO")["delta"], "results/method_table.md", "results/preference.md")
    put("simpo_delta", row("SimPO")["delta"], "results/method_table.md", "results/preference.md")
    items = csv_rows("results/tidy/items_long.csv")
    r_pass = lambda arm: sum(int(r["pass"]) for r in items if r["arm"] == arm and r["block"] == "R")
    n_r = sum(1 for r in items if r["arm"] == "l14b_sft_rslora_tok-s0-v1.2" and r["block"] == "R")
    put("rft_r_sft", r_pass("l14b_sft_rslora_tok-s0-v1.2"))
    put("rft_r_rft", r_pass("l14b_sft_rslora_tok-s0-v1.2_rft"))
    put("n_r", n_r)

    # safety
    for key, prefix in [("base", "Base, Qwen3-14B"), ("sft", "SFT rsLoRA with token rows, data v1.2"),
                        ("dpo", "DPO"), ("simpo", "SimPO")]:
        put(f"rt_{key}", row(prefix)["redteam"], "results/method_table.md", "results/redteam.md")
    rt0 = MT.redteam(MT.SFT_V12_S0)
    put("rt_sft0", rt0, "results/preference.md")
    put("rt_sft_seeds", row("SFT rsLoRA with token rows, data v1.2")["seeds"], "results/method_table.md")

    # serving: training (results/lora_vs_qlora.md) and CPU GGUF speed (results/gguf_demo_models.md)
    lq = md_rows("results/lora_vs_qlora.md")
    hdr, body = lq[0], [r for r in lq[1:] if len(r) == len(lq[0])]
    want = ["Arm", "n", "Assistant /200", "Peak train VRAM (GB)", "Tokens/s", "Train wall-clock (min)"]
    idx = [hdr.index(w) for w in want]
    L = ["| " + " | ".join(want) + " |", "|" + "---|" * len(want)]
    for r in body:
        L.append("| " + " | ".join(r[i] for i in idx) + " |")
        checks.extend((r[i], "results/lora_vs_qlora.md") for i in idx[1:])
    V["train_table"] = "\n".join(L)
    speed_md = read("results/gguf_demo_models.md").split("## Speed with", 1)[1]
    put("speed_note", re.search(r"\*\*(.+?)\.?\*\*", speed_md).group(1), "results/gguf_demo_models.md")
    sp = md_rows("results/gguf_demo_models.md", "Speed with 2 threads")
    shdr = sp[0]
    want = ["Model", "Decode tokens/s", "End-to-end tokens/s", "TTFT median / p90 / max, warm (s)", "Peak RAM (GB)"]
    idx = [shdr.index(w) for w in want]
    L = ["| " + " | ".join(want) + " |", "|" + "---|" * len(want)]
    for r in sp[1:]:
        if r[1] == MT.GGUF_QUANT:
            L.append("| " + " | ".join(r[i] for i in idx) + " |")
            checks.extend((r[i], "results/gguf_demo_models.md") for i in idx[1:])
    V["speed_table"] = "\n".join(L)

    # local demo
    cfg = json.loads(read("space/config.json"))
    put("demo_address", f"http://127.0.0.1:{cfg['server_port']}")
    files = [r["comp"] for r in T["rows"] if r["method"].startswith("GGUF")]
    put("n_gguf", len(files))
    V["demo_commands"] = "\n".join([
        "```",
        f"git clone {REPO}.git && cd chinor-bank-assistant-public",
        "pip install -r space/requirements.txt",
        "# Linux / macOS",
        "CHINOR_MODELS_DIR=<folder with the four *-Q8_0.gguf files> python space/app.py",
        "# Windows PowerShell",
        '$env:CHINOR_MODELS_DIR="<folder with the four *-Q8_0.gguf files>"; python space/app.py',
        "```"])
    V["gguf_files"] = ", ".join(f"`{n}-{MT.GGUF_QUANT}.gguf`" for _, n in MT.GGUF)

    # citations
    bib = re.search(r"```\n(\s*@inproceedings\{Casanueva2020.*?)\n\s*```", read("data/DATA_SOURCES.md"), re.S)
    V["banking77_bibtex"] = "```bibtex\n" + textwrap.dedent(bib.group(1)).rstrip() + "\n```"
    V["citation_bibtex"] = "```bibtex\n" + cff_bibtex() + "\n```"
    return V, checks


def cff_bibtex() -> str:
    """BibTeX from CITATION.cff (preferred-citation: authors, title, year, url)."""
    cff = read("CITATION.cff")
    pref = cff.split("preferred-citation:", 1)[1]
    given = re.search(r"given-names:\s*(.+)", pref).group(1).strip()
    family = re.search(r"family-names:\s*(.+)", pref).group(1).strip()
    title = re.search(r'title:\s*"(.+)"', pref).group(1)
    year = re.search(r"year:\s*(\d+)", pref).group(1)
    url = re.search(r'url:\s*"(.+)"', pref).group(1)
    key = f"{family}{year}{title.split()[0]}"
    return (f"@software{{{key},\n  author = {{{family}, {given}}},\n  title = {{{title}}},\n  year = {{{year}}},\n"
            f"  url = {{{url}}}\n}}")


def build() -> tuple[str, list[dict], list[tuple[str, str]]]:
    """(README text, spans of the filled placeholders, checks)."""
    V, checks = values()
    tpl = TEMPLATE.read_text(encoding="utf-8")
    out, spans, pos = [], [], 0
    length = 0
    for m in PLACEHOLDER.finditer(tpl):
        out.append(tpl[pos:m.start()])
        length += m.start() - pos
        kind, arg = m["kind"], m["arg"]
        if kind in "vb":
            if arg not in V:
                raise SystemExit(f"no value {arg!r} for the template")
            text, meta = V[arg], {"name": arg}
        else:
            path, start, *end = arg.split("|")
            text, meta = quote(path, start, end[0] if end else None), {"path": path}  # checked by test (c)
        spans.append({"start": length, "end": length + len(text), "kind": kind, **meta})
        out.append(text)
        length += len(text)
        pos = m.end()
    out.append(tpl[pos:])
    return "".join(out), spans, checks


def main() -> None:
    text, _, _ = build()
    if "--check" in sys.argv:
        ok = TARGET.read_text(encoding="utf-8") == text
        print("ok" if ok else "README.md differs from a fresh build: run python scripts/build_readme.py")
        sys.exit(0 if ok else 1)
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"README.md: {len(text.splitlines())} lines")


if __name__ == "__main__":
    main()

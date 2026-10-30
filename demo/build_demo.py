"""demo/index.html: a static demo page built from saved eval-v1 answers (no live model).

python demo/build_demo.py
For 3 items per assistant block (T-seen, T-held, B1, B2, B3, B4; the first ids in eval/eval_set.jsonl with a single
user turn; multi-turn items are skipped for brevity) the page shows the customer message and the answer of
each arm that exists: base 14B (0-shot), SFT 14B rsLoRA v1.2 seed 0, DPO (rules) seed 0, SimPO (rules) seed 0, each with
its scorer verdict (eval/outputs/<arm>/scores.jsonl). Fictional bank; all data fictional. Self-contained HTML, light
and dark theme.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "outputs"
ARMS = [("Base 14B (no fine-tuning)", "base-14B-0shot-A"), ("SFT (14B rsLoRA)", "l14b_sft_rslora_tok-s0-v1.2"),
        ("DPO (rules)", "pref_dpo_rules-s0"), ("SimPO (rules)", "pref_simpo_rules-s0")]
BLOCKS = {"T-seen": "Banking question (trained topic)", "T-held": "Banking question (held-out topic)",
          "B1": "Missing detail: should ask", "B2": "Out of scope: should decline", "B3": "Safety / prompt injection",
          "B4": "About the assistant"}
PER_BLOCK = 3


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    items = [it for it in jsonl(ROOT / "eval" / "eval_set.jsonl") if it["block"] in BLOCKS and len(it["messages"]) == 1]
    arms = []
    for name, arm in ARMS:
        if (OUT / arm / "answers.jsonl").exists() and (OUT / arm / "scores.jsonl").exists():
            ans = {a["id"]: a["raw"] for a in jsonl(OUT / arm / "answers.jsonl")}
            sc = {s["id"]: s for s in jsonl(OUT / arm / "scores.jsonl")}
            arms.append((name, ans, sc))
    sections = []
    for b, title in BLOCKS.items():
        cards = []
        for it in [i for i in items if i["block"] == b][:PER_BLOCK]:
            cols = "".join(
                f'<div class="ans"><div class="who">{html.escape(n)} <span class="{"ok" if sc[it["id"]]["pass"] else "no"}">'
                f'{"✓ pass" if sc[it["id"]]["pass"] else "✗ fail"}</span></div><p>{html.escape(ans[it["id"]].strip())}</p>'
                + ("" if sc[it["id"]]["pass"] else f'<div class="why">{html.escape(sc[it["id"]]["reason"])}</div>') + "</div>"
                for n, ans, sc in arms)
            cards.append(f'<article><div class="q"><span class="id">{it["id"]}</span> {html.escape(it["messages"][0]["content"])}'
                         f'</div><div class="grid">{cols}</div></article>')
        sections.append(f"<section><h2>{html.escape(title)}</h2>{''.join(cards)}</section>")
    page = TEMPLATE.replace("{{ARMS}}", ", ".join(n for n, _, _ in arms)).replace("{{BODY}}", "".join(sections))
    (ROOT / "demo" / "index.html").write_text(page, encoding="utf-8", newline="\n")
    print(f"demo/index.html: {len(arms)} arms ({', '.join(n for n, _, _ in arms)}), {sum(c.count('<article') for c in sections)} items")


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chinor Assistant Demo</title>
<style>
:root{--bg:#fafaf8;--card:#fff;--ink:#1d1d1b;--muted:#5f5f5a;--line:#e3e2dc;--ok:#1f7a3a;--no:#b3261e;--q:#f1f0ea}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161615;--card:#1f1f1d;--ink:#ecebe6;--muted:#a3a29b;--line:#34332f;--ok:#6fcf8b;--no:#ff8a80;--q:#2a2926}}
:root[data-theme="dark"]{--bg:#161615;--card:#1f1f1d;--ink:#ecebe6;--muted:#a3a29b;--line:#34332f;--ok:#6fcf8b;--no:#ff8a80;--q:#2a2926}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1200px;margin:0 auto;padding:24px 16px 64px}h1{font-size:1.6rem;margin:0 0 4px}h2{font-size:1.1rem;margin:36px 0 12px}
.lead{color:var(--muted);max-width:760px}article{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:12px 0;overflow:hidden}
.q{background:var(--q);padding:12px 16px;font-weight:600}.id{font:12px ui-monospace,monospace;color:var(--muted);margin-right:6px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}.ans{padding:12px 16px;border-top:1px solid var(--line);border-left:1px solid var(--line)}
.ans p{margin:6px 0 0;white-space:pre-wrap;overflow-wrap:anywhere}.who{font-size:13px;color:var(--muted);font-weight:600}
.ok{color:var(--ok)}.no{color:var(--no)}.why{font-size:12px;color:var(--muted);margin-top:6px}
</style></head><body><main>
<h1>Chinor Bank Assistant: saved answers</h1>
<p class="lead">Chinor is a fictional bank; every name, number and policy here is invented. This page is static: the answers were
generated once on the frozen eval set (greedy decoding, Protocol A) and are shown with the automatic scorer's verdict.
Arms: {{ARMS}}.</p>
{{BODY}}
</main></body></html>
"""

if __name__ == "__main__":
    main()

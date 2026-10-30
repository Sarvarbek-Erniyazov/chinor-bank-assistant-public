"""docs/site/index.html: the project's GitHub Pages landing page (static; no build step on GitHub).

python docs/site/build_site.py [--repo-url https://github.com/<user>/<repo>]
Publish with GitHub Pages from the main branch, folder / (root): the page is served at <pages-url>/docs/site/ and
the root index.html redirects there. It reads figures/ (light and dark PNG via <picture>), demo/index.html (embedded)
and the claims table of docs/claims.md, so it never duplicates numbers by hand; rerun after the figures change.
"""
from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = "../../"  # from docs/site/ to the repository root (figures, demo: served by Pages)
SRC = "<repo-url>/blob/main/"  # markdown files: rendered on GitHub, not by Pages; set by --repo-url
FIGS = [("F0", "Pipeline and hand audits"), ("F1", "Assistant score per arm"), ("F3", "What SFT changes, per block"),
        ("F14", "Proof: end-of-turn fix and DPO start"), ("F11", "Safety flags per arm"), ("F15", "What did not work")]


def md_inline(t: str) -> str:
    t = html.escape(t, quote=False).replace("\\|", "|")
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<a href="{SRC}docs/{m.group(2)}">{m.group(1)}</a>', t)


def claims_table() -> tuple[str, str]:
    text = (ROOT / "docs" / "claims.md").read_text(encoding="utf-8")
    rows = [l for l in text.splitlines() if l.startswith("| ") and not l.startswith("|---")]
    cells = lambda l: [c.strip() for c in re.split(r"(?<!\\)\|", l)[1:-1]]
    head = "".join(f"<th>{md_inline(c)}</th>" for c in cells(rows[0]))
    body = "".join("<tr>" + "".join(f"<td>{md_inline(c)}</td>" for c in cells(r)) + "</tr>" for r in rows[1:])
    dont = text[text.index("## Do not claim"):].splitlines()[1:]
    items = "".join(f"<li>{md_inline(l[2:])}</li>" for l in dont if l.startswith("- "))
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>", f"<ul>{items}</ul>"


def picture(fid: str, alt: str) -> str:
    return (f'<figure><picture><source media="(prefers-color-scheme: dark)" srcset="{REPO}figures/{fid}_dark.png">'
            f'<img src="{REPO}figures/{fid}_light.png" alt="{html.escape(alt)}" loading="lazy"></picture>'
            f'<figcaption>{fid} — {html.escape(alt)} (<a href="{SRC}docs/figures.md#{fid.lower()}">caption and test</a>)</figcaption></figure>')


def main():
    global SRC
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-url", default="<repo-url>")
    SRC = ap.parse_args().repo_url.rstrip("/") + "/blob/main/"
    table, dont = claims_table()
    figs = "".join(picture(f, a) for f, a in FIGS)
    sections = [("what-was-built", "What was built"), ("main-results", "Main results"), ("stage-effects", "Stage effects"),
                ("proof-figures", "Proof figures"), ("can-the-numbers-be-trusted", "Trust"), ("what-didnt-work", "What didn't work"),
                ("safety", "Safety"), ("run-it", "Run it"), ("limitations", "Limitations")]
    links = " · ".join(f'<a href="{SRC}README.md#{a}">{t}</a>' for a, t in sections)
    page = TEMPLATE.format(R=REPO, S=SRC, figs=figs, table=table, dont=dont, links=links)
    (ROOT / "docs" / "site" / "index.html").write_text(page, encoding="utf-8", newline="\n")
    print(f"docs/site/index.html: {len(FIGS)} figures, claims table {table.count('<tr>') - 1} rows")


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chinor Bank Assistant</title>
<meta name="description" content="Post-training study: Qwen3 base models turned into the support assistant of a fictional bank, measured on frozen evals.">
<style>
:root{{--bg:#fafaf8;--card:#fff;--ink:#1d1d1b;--muted:#5f5f5a;--line:#e3e2dc;--accent:#0072B2;--warn:#fff4d6}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181c;--card:#1f2125;--ink:#ecebe6;--muted:#a3a29b;--line:#34363b;--accent:#56B4E9;--warn:#3a3220}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1080px;margin:0 auto;padding:28px 16px 72px}}h1{{font-size:1.9rem;margin:0 0 6px}}h2{{margin:44px 0 12px;font-size:1.3rem}}
a{{color:var(--accent)}}.lead{{color:var(--muted);max-width:760px}}.notice{{background:var(--warn);border-radius:8px;padding:10px 14px;font-size:.92rem}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:18px 0}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}}
.stat b{{display:block;font-size:1.7rem;line-height:1.2}}.stat span{{color:var(--muted);font-size:.9rem}}
ul.find li{{margin:4px 0}}figure{{margin:18px 0;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}}
figure img{{width:100%;height:auto;display:block}}figcaption{{color:var(--muted);font-size:.85rem;margin-top:6px}}
.tablewrap{{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card)}}
table{{border-collapse:collapse;font-size:.85rem;min-width:820px}}th,td{{text-align:left;vertical-align:top;padding:7px 10px;border-bottom:1px solid var(--line)}}
th{{position:sticky;top:0;background:var(--card)}}code{{font-size:.88em}}
iframe{{width:100%;height:720px;border:1px solid var(--line);border-radius:10px;background:var(--card)}}
nav{{font-size:.92rem;color:var(--muted)}}
</style></head><body><main>
<h1>Chinor Bank Assistant</h1>
<p class="notice"><strong>Fiction notice.</strong> Chinor Bank does not exist. Every policy, fee, limit, phone number and
timing here was invented for the project and differs from industry defaults on purpose. Nothing here describes, imitates
or is affiliated with any real bank.</p>
<p class="lead">A post-training study: Qwen3 <em>base</em> models are turned into the customer-support assistant of a
fictional bank, and every training stage is measured on one frozen eval set (220 items) and a frozen red-team set (60
attacks). Code, data and every number: <a href="{S}README.md">README</a>.</p>

<h2 id="summary">Read this in 2 minutes</h2>
<div class="stats">
<div class="stat"><b>45 → 145.0</b><span>Assistant score /200, 14B base → SFT (rsLoRA, 5 seeds, ± 2.5)</span></div>
<div class="stat"><b>13.3 % → 2.3 %</b><span>red-team attack success, 14B base → SFT</span></div>
<div class="stat"><b>0 % → 100 %</b><span>turns ending on &lt;|im_end|&gt; once the two token rows are trained</span></div>
</div>
<ul class="find">
<li><strong>Headline:</strong> supervised fine-tuning does almost all the work: +100 /200 [93, 107] over the base model, well above Qwen3-14B Instruct (58).</li>
<li><strong>Headline:</strong> the red-team rate falls from 13.3 % to 2.3 %; the scorer agreed with the author on 28 of 30 blind answers.</li>
<li><strong>Negative:</strong> on banking topics never trained on, the models recall the answer to a different topic (0–2 / 20).</li>
<li><strong>Negative:</strong> they rarely ask for a missing detail (0–1 / 20), and three SFT data versions did not change that.</li>
<li><strong>Negative:</strong> DPO and SimPO on 348 rule-labelled on-policy pairs changed nothing measurable.</li>
</ul>
<nav>README sections: {links}</nav>

<h2 id="figures">Figures</h2>
{figs}

<h2 id="claims">Claims</h2>
<div class="tablewrap">{table}</div>
<h3>Do not claim</h3>
{dont}

<h2 id="demo">Demo (saved answers, side by side)</h2>
<p class="lead">Static: answers generated once on the frozen eval set (greedy) with the scorer's verdict. Live mode:
<code>python demo/app.py --model … --adapter …</code> (<a href="{S}README.md#run-it">Run it</a>).</p>
<iframe src="{R}demo/index.html" title="Chinor demo: saved answers of base, SFT, DPO and SimPO"></iframe>

<h2 id="licence">Licence</h2>
<p>Code Apache-2.0; project data CC BY 4.0 (<a href="{S}LICENSE-DATA">LICENSE-DATA</a>). Banking77 queries CC BY 4.0
(Casanueva et al. 2020); Qwen3 Apache-2.0. Evaluation data — do not train on (canary in <code>eval/FROZEN.md</code>).</p>
</main></body></html>
"""

if __name__ == "__main__":
    main()

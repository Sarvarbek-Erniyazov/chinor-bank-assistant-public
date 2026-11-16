"""demo/viewer/: a static viewer of every recorded answer behind figures/T1.md and results/redteam.md (no model).

python demo/build_viewer.py [--out demo/viewer]
Built from committed files only: eval/eval_set.jsonl, eval/redteam_set.jsonl, eval/outputs/<run>/{answers.jsonl,
scores.jsonl, redteam_scores.jsonl, run.json}, results/runs/<run>/train/run.json, results/adapter_sha256.tsv,
results/model_sha256.tsv, figures/T1.md, results/redteam.md, docs/limitations.md and data/DATA_SOURCES.md (banner wording).
Every arm and seed of T1 (eval-v1, 220 items) and of results/redteam.md (redteam-v1, 60 items) is included.

Writes <out>/index.html (page, styles and code), <out>/data/core.js (items, runs, per-cell pass / flags / stop reason,
and the recorded T1 / redteam.md totals) and <out>/data/answers_<e|r>_<nn>.js (full raw answers, scorer reasons and
cut offsets, ITEMS_PER_CHUNK items each, loaded on demand). Plain <script> files, so the page works from the file
system (file://) and on GitHub Pages. The page computes the per-arm totals itself from core.js and shows them next to
the recorded values; tests/test_viewer.py checks both.

Cut marker: the scorer (eval/score.py clean_answer) reads an answer up to its first stop string (<|im_end|>,
<|endoftext|>, <|im_start|>); the page shows the full raw answer with a marker at that point. The exploratory
"cut" score of results/lora_no_token_rows.md (eval/turn_cut.py) cuts earlier, at an invented next turn; it is
marked separately and is not the official score.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from score import STOP_STRINGS  # noqa: E402
from turn_cut import CUT  # noqa: E402

OUT = ROOT / "eval" / "outputs"
ITEMS_PER_CHUNK = 10
FLAG_KEYS = ["hard_violation", "over_refusal", "injection_success", "fabricated_number"]
STOP_CODES = ["im_end", "endoftext", "length"]
# Banner: each text must occur verbatim (after whitespace normalisation) in its source file.
BANNER = [
    ("Lenient scorer", "docs/limitations.md",
     "51/60 = 0.85 [0.74, 0.92] agreement with one annotator; errors lenient (8 of 9): automatic Assistant scores are "
     "upper bounds"),
    ("One annotator", "docs/limitations.md",
     "Independent human inter-annotator agreement: not measured; all hand labels by one annotator (intra-rater "
     "re-marking not done). The annotator (the project author) also wrote the eval and red-team sets and the handbook."),
    ("Canonical-answer eval", "docs/limitations.md",
     "teaches one fixed answer per intent, so the eval measures recall on T-seen, not generalisation from the handbook."),
    ("Fictional bank", "data/DATA_SOURCES.md",
     "Chinor Bank does not exist; every policy and number in this repository was invented."),
]


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def check_banner() -> None:
    for label, src, text in BANNER:
        if squash(text) not in squash((ROOT / src).read_text(encoding="utf-8")):
            raise SystemExit(f"banner text '{label}' no longer occurs in {src}; update BANNER")


def t1_rows() -> list[dict]:
    """figures/T1.md rows: arm id, size, label, seeds, recorded Assistant /200 (mean, sd) and retention."""
    rows = []
    for line in (ROOT / "figures" / "T1.md").read_text(encoding="utf-8").splitlines():
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) < 12:
            continue
        m = re.match(r"(.*) \(`([^`]+)`\)$", c[1])
        if not m or not c[2].isdigit():
            continue
        rows.append({"arm": m.group(2), "label": m.group(1), "size": c[0], "seeds": int(c[2]),
                     "assistant": c[3], "retention": c[11]})
    return rows


def rt_rows() -> list[dict]:
    """results/redteam.md first table: arm, method, size, seeds, recorded attack_success and safe_and_helpful."""
    rows = []
    for line in (ROOT / "results" / "redteam.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*([\d.]+) %[^(]*\((\d+)/(\d+);[^|]*\|"
                     r"[^|]*\|\s*([\d.]+) %[^(]*\((\d+)/(\d+);", line)
        if m and not any(r["arm"] == m.group(1) for r in rows):
            rows.append({"arm": m.group(1), "method": m.group(2), "size": m.group(3), "seeds": int(m.group(4)),
                         "attack_pct": m.group(5), "attack_k": int(m.group(6)), "n": int(m.group(7)),
                         "safe_pct": m.group(8), "safe_k": int(m.group(9))})
    return rows


def run_dirs(arm: str, seeds: int, prefix: str) -> list[tuple[str, int | None]]:
    """eval/outputs folders of an arm: '<prefix><base>-s<seed><-vX>' for trained arms, '<prefix><arm>' otherwise."""
    if arm.startswith(("base-", "ref-")):
        found = [(prefix + arm, None)] if (OUT / (prefix + arm)).is_dir() else []
    else:
        base, suffix = re.match(r"^(.*?)(-v[\w.]+)?$", arm).groups()
        pat = re.compile("^" + re.escape(prefix + base) + r"-s(\d+)" + re.escape(suffix or "") + "$")
        found = sorted(((d.name, int(m.group(1))) for d in OUT.iterdir() if (m := pat.match(d.name))), key=lambda x: x[1])
    if len(found) != seeds:
        raise SystemExit(f"{prefix}{arm}: {len(found)} run folders, expected {seeds}")
    return found


def sha_tables() -> dict[str, tuple[str, str]]:
    out = {}
    for l in (ROOT / "results" / "adapter_sha256.tsv").read_text(encoding="utf-8").splitlines()[1:]:
        p = l.split("\t")
        out[p[0]] = (p[1], "adapter_model.safetensors (results/adapter_sha256.tsv)")
    for l in (ROOT / "results" / "model_sha256.tsv").read_text(encoding="utf-8").splitlines():
        p = l.split("\t")
        if len(p) >= 3:
            out.setdefault(p[0], (p[2], f"{p[1]} (results/model_sha256.tsv)"))
    return out


def run_meta(dirname: str, shas: dict) -> dict:
    stem = dirname[3:] if dirname.startswith("rt-") else dirname
    ev = json.loads((OUT / dirname / "run.json").read_text(encoding="utf-8"))
    meta = {"eval_run_json": f"eval/outputs/{dirname}/run.json", "model": ev.get("model"),
            "protocol": ev.get("protocol"), "shots": ev.get("shots")}
    tp = ROOT / "results" / "runs" / stem / "train" / "run.json"
    if tp.exists():
        t = json.loads(tp.read_text(encoding="utf-8"))
        meta.update(train_run_json=f"results/runs/{stem}/train/run.json", config=t.get("config"), seed=t.get("seed"),
                    data=t.get("data_dir") or t.get("pairs"))
        if t.get("pairs"):
            meta["parent"] = "sft-merged-l14b-v1.2-s0 (merged l14b_sft_rslora_tok-s0-v1.2)"
    if stem in shas:
        meta["sha256"], meta["sha256_of"] = shas[stem]
    return meta


def cut_offsets(raw: str) -> tuple[int, int]:
    """Raw-string offsets where the scorer stops reading (-1: reads it all) and where turn_cut cuts (-1: no cut)."""
    stop = min([k for k in (raw.find(s) for s in STOP_STRINGS) if k != -1], default=-1)
    clean = raw[:stop] if stop != -1 else raw
    lead = len(clean) - len(clean.lstrip())
    m = CUT.search(clean.strip())
    turn = lead + m.start() if m else -1
    return stop, turn


def build(out: Path) -> dict:
    check_banner()
    shas = sha_tables()
    ev_items = jsonl(ROOT / "eval" / "eval_set.jsonl")
    rt_items = [r for r in jsonl(ROOT / "eval" / "redteam_set.jsonl") if r.get("id") != "_canary"]
    assert len(ev_items) == 220 and len(rt_items) == 60
    kinds = {
        "e": {"name": "eval-v1", "items": ev_items, "arms": t1_rows(), "prefix": ""},
        "r": {"name": "redteam-v1", "items": rt_items, "arms": rt_rows(), "prefix": "rt-"},
    }
    core = {"banner": [{"label": l, "source": s, "text": t} for l, s, t in BANNER], "flag_keys": FLAG_KEYS,
            "stop_codes": STOP_CODES, "items_per_chunk": ITEMS_PER_CHUNK, "kinds": {}}
    chunks: dict[str, dict] = {}
    for k, K in kinds.items():
        items = sorted(K["items"], key=lambda it: it["id"])
        order = {it["id"]: i for i, it in enumerate(items)}
        runs, cells = [], []
        for arm in K["arms"]:
            for dirname, seed in run_dirs(arm["arm"], arm["seeds"], K["prefix"]):
                ans = {a["id"]: a for a in jsonl(OUT / dirname / "answers.jsonl")}
                sc_file = OUT / dirname / ("scores.jsonl" if k == "e" else "redteam_scores.jsonl")
                sc = {s["id"]: s for s in jsonl(sc_file)}
                assert set(ans) == set(order) == set(sc), dirname
                runs.append({"id": dirname, "arm": arm["arm"], "seed": seed, "meta": run_meta(dirname, shas)})
                row = [None] * len(items)
                for iid, i in order.items():
                    a, s = ans[iid], sc[iid]
                    stop = STOP_CODES.index(a["stop_reason"])
                    if k == "e":
                        flags = sum(1 << b for b, f in enumerate(FLAG_KEYS) if s["flags"][f])
                        row[i] = [int(s["pass"]), flags, stop]
                        detail = {"reason": s["reason"]}
                    else:
                        row[i] = [int(not s["attack_success"]), int(s["safe_and_helpful"]), stop]
                        detail = {"pass_rule": s["pass_rule"], "violations": s["violations"], "unmet": s["unmet"]}
                    so, to = cut_offsets(a["raw"])
                    key = f"{k}_{i // ITEMS_PER_CHUNK:02d}"
                    chunks.setdefault(key, {}).setdefault(iid, {})[dirname] = {"raw": a["raw"], "stop_at": so,
                                                                                "turn_cut": to, **detail}
                cells.append(row)
        if k == "e":
            items_out = [{"id": it["id"], "block": it["block"], "messages": it["messages"],
                          "rubric": {f: it[f] for f in ("required_facts", "expected", "slot_keyword", "attack_type",
                                                        "notes", "fail_markers", "pass_markers", "success_markers")
                                     if it.get(f) not in (None, [], "")}} for it in items]
        else:
            items_out = [{"id": it["id"], "block": it["attack_type"], "messages": it["messages"],
                          "rubric": {f: it[f] for f in ("pass_rule", "markers", "required_facts", "must_markers")
                                     if it.get(f) not in (None, [], "")}} for it in items]
        core["kinds"][k] = {"name": K["name"], "items": items_out, "runs": runs, "cells": cells, "recorded": K["arms"]}
    out.mkdir(parents=True, exist_ok=True)
    (out / "data").mkdir(exist_ok=True)
    for old in (out / "data").glob("answers_*.js"):
        if old.stem[len("answers_"):] not in chunks:
            old.unlink()
    write_js(out / "data" / "core.js", "window.VIEWER_CORE = ", core, ";\n")
    for key, payload in sorted(chunks.items()):
        write_js(out / "data" / f"answers_{key}.js", f"window.VIEWER_CHUNK({json.dumps(key)}, ", payload, ");\n")
    (out / "index.html").write_text(PAGE, encoding="utf-8", newline="\n")
    return core


def write_js(path: Path, head: str, obj, tail: str) -> None:
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    path.write_text(head + body + tail, encoding="utf-8", newline="\n")


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chinor Answer Viewer</title>
<meta name="description" content="Every recorded eval-v1 and redteam-v1 answer of the Chinor Bank Assistant runs, with scorer verdicts. Fictional bank; no model.">
<style>
:root{--bg:#ffffff;--fg:#1b1d21;--muted:#5d636e;--line:#d9dce2;--card:#f6f7f9;--pass:#1d6b3a;--pass-bg:#e3f3e8;--fail:#a1261b;--fail-bg:#fbe7e4;--warn-bg:#fff4d6;--warn-fg:#6b4d00;--accent:#2756a8;--after:#8a909b;--mark:#c2410c}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#14161a;--fg:#e6e8ec;--muted:#9aa1ad;--line:#2c3038;--card:#1c1f25;--pass:#7fd39b;--pass-bg:#173323;--fail:#ff9b8f;--fail-bg:#3a1c19;--warn-bg:#352a0c;--warn-fg:#f1d58a;--accent:#8fb3ff;--after:#7b818c;--mark:#fb923c}}
:root[data-theme="dark"]{--bg:#14161a;--fg:#e6e8ec;--muted:#9aa1ad;--line:#2c3038;--card:#1c1f25;--pass:#7fd39b;--pass-bg:#173323;--fail:#ff9b8f;--fail-bg:#3a1c19;--warn-bg:#352a0c;--warn-fg:#f1d58a;--accent:#8fb3ff;--after:#7b818c;--mark:#fb923c}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent)}
code,pre,.mono{font-family:ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace;font-size:13px}
.banner{position:sticky;top:0;z-index:5;background:var(--warn-bg);color:var(--warn-fg);border-bottom:1px solid var(--line);padding:8px 16px}
.banner ul{margin:4px 0 0;padding-left:18px}.banner li{margin:2px 0}.banner .src{opacity:.8;font-size:12px}
.banner button{float:right;margin-left:8px}
.banner .short{display:none}
.banner.collapsed ul{display:none}.banner.collapsed .short{display:inline}
@media (max-width:700px){.banner{font-size:13px;padding:6px 12px}.banner ul{max-height:34vh;overflow-y:auto}}
main{max-width:1100px;margin:0 auto;padding:12px 16px 48px}
h1{font-size:20px;margin:8px 0}
.controls{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;margin:8px 0 12px}
select,button,input{font:inherit;color:var(--fg);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:4px 8px}
button{cursor:pointer}
details.arms{border:1px solid var(--line);border-radius:6px;padding:4px 8px;background:var(--card)}
details.arms label{display:inline-block;margin:2px 10px 2px 0;font-size:13px}
.nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0}
.count{color:var(--muted);font-size:13px}
.item{border:1px solid var(--line);border-radius:8px;padding:12px;margin:8px 0;background:var(--card)}
.item h2{font-size:17px;margin:0 0 6px}
.turn{margin:4px 0;white-space:pre-wrap;overflow-wrap:anywhere}.turn b{color:var(--muted)}
.rubric{font-size:13px;margin-top:6px}.rubric div{overflow-wrap:anywhere}
.armgroup{margin-top:14px}.armgroup h3{font-size:15px;margin:0 0 4px}
.cell{border:1px solid var(--line);border-radius:8px;margin:6px 0;padding:8px;background:var(--bg)}
.cell header{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;font-size:13px}
.badge{font-weight:600;border-radius:4px;padding:0 6px}
.badge.pass{color:var(--pass);background:var(--pass-bg)}.badge.fail{color:var(--fail);background:var(--fail-bg)}
.flag{color:var(--fail);font-size:12px;border:1px solid var(--fail);border-radius:4px;padding:0 4px}
.meta{color:var(--muted);font-size:12px;overflow-wrap:anywhere}
pre.raw{white-space:pre-wrap;overflow-wrap:anywhere;margin:6px 0 0;padding:8px;border-radius:6px;background:var(--card)}
pre.raw .after{color:var(--after)}
.cut{color:var(--mark);font-weight:700}
.reason{font-size:13px;margin-top:4px;overflow-wrap:anywhere}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:4px 6px;text-align:left;vertical-align:top}
.tablewrap{overflow-x:auto}
.bad{color:var(--fail);font-weight:700}.ok{color:var(--pass)}
footer{color:var(--muted);font-size:12px;margin-top:24px}
</style>
</head>
<body>
<div class="banner" id="banner"></div>
<main>
<h1>Chinor answer viewer</h1>
<p class="count">Every recorded answer of every arm and seed in <code>figures/T1.md</code> (eval-v1, 220 items) and <code>results/redteam.md</code> (redteam-v1, 60 items), with the automatic scorer's verdict. Items are in id order; nothing is curated. Recorded outputs only: no model runs here.</p>
<div class="controls">
  <label>Set <select id="kind"><option value="e">eval-v1</option><option value="r">redteam-v1</option></select></label>
  <label>Block <select id="block"></select></label>
  <label><input type="checkbox" id="failonly"> failures only</label>
  <label><input type="checkbox" id="disagree"> arms disagree</label>
  <button id="random" type="button">Random item</button>
  <button id="theme" type="button" aria-label="Toggle light or dark theme">Theme</button>
</div>
<details class="arms" id="armbox"><summary>Arms (<span id="armcount"></span>)</summary><div id="armlist"></div><button type="button" id="armall">all</button> <button type="button" id="armnone">none</button></details>
<p class="count" id="filterhelp"></p>
<div class="nav"><button id="prev" type="button">&larr; Prev</button><select id="jump" aria-label="Item"></select><button id="next" type="button">Next &rarr;</button><span class="count" id="pos"></span></div>
<div id="view"></div>
<details id="totalsbox"><summary><b>Per-arm totals</b> (computed in this page from the same data, next to the recorded table)</summary><div class="tablewrap" id="totals"></div></details>
<footer>Built by <code>demo/build_viewer.py</code> from committed files. Pass/fail is the automatic rubric scorer (<code>eval/score.py</code>, <code>eval/redteam_score.py</code>); see the banner for its limits.</footer>
</main>
<script src="data/core.js"></script>
<script>
"use strict";
const C = window.VIEWER_CORE, chunks = {}, waiting = {};
window.VIEWER_CHUNK = (key, data) => { chunks[key] = data; (waiting[key] || []).forEach(f => f()); delete waiting[key]; };
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const store = {get(k){try{return localStorage.getItem(k)}catch(e){return null}}, set(k,v){try{localStorage.setItem(k,v)}catch(e){}}};
const REL = "../../";  // repo root, relative to demo/viewer/
let S = {kind: "e", block: "", failonly: false, disagree: false, arms: null, idx: 0};

function banner(){
  const b = $("banner"), collapsed = store.get("viewer-banner") === "collapsed";
  b.innerHTML = '<button type="button" id="bt">' + (collapsed ? "show" : "hide") + '</button><b>Read before judging any answer.</b>' +
    '<span class="short"> ' + C.banner.map(x => esc(x.label)).join(" · ") + '</span><ul>' +
    C.banner.map(x => '<li><b>' + esc(x.label) + ':</b> ' + esc(x.text) + ' <span class="src">(' + esc(x.source) + ')</span></li>').join("") + '</ul>';
  b.classList.toggle("collapsed", collapsed);
  $("bt").onclick = () => { store.set("viewer-banner", b.classList.contains("collapsed") ? "open" : "collapsed"); banner(); };
}
function K(){ return C.kinds[S.kind]; }
function failed(cell){ return cell[0] === 0; }  // eval: pass==0; redteam: cell[0] = 1 - attack_success
function armsOn(){ const k = K(); return k.recorded.map(a => a.arm).filter(a => !S.arms || S.arms.has(a)); }
function runIdx(){ const on = new Set(armsOn()); return K().runs.map((r, i) => on.has(r.arm) ? i : -1).filter(i => i >= 0); }
function itemList(){
  const k = K(), ri = runIdx(), out = [];
  k.items.forEach((it, i) => {
    if (S.block && it.block !== S.block) return;
    const cs = ri.map(r => k.cells[r][i]);
    if (S.failonly && !cs.some(failed)) return;
    if (S.disagree && !(cs.some(failed) && cs.some(c => !failed(c)))) return;
    out.push(i);
  });
  return out;
}
function loadChunk(key, cb){
  if (chunks[key]) return cb();
  (waiting[key] = waiting[key] || []).push(cb);
  if (waiting[key].length > 1) return;
  const s = document.createElement("script"); s.src = "data/answers_" + key + ".js";
  s.onerror = () => { $("view").innerHTML = '<p class="bad">Could not load data/answers_' + esc(key) + '.js</p>'; };
  document.head.appendChild(s);
}
function rawHtml(d){
  const raw = d.raw, stop = d.stop_at, turn = d.turn_cut;
  const mk = (t) => '<span class="cut" title="' + esc(t) + '">' + (t.startsWith("scorer") ? "✂ scorer stops reading here" : "⋯ turn-cut (exploratory only)") + '</span>';
  let html = "";
  if (turn >= 0 && (stop < 0 || turn < stop)) {
    html += esc(raw.slice(0, turn)) + mk("turn-cut: where eval/turn_cut.py ends the intended turn; used only by the exploratory cut score, not the official score");
    html += stop >= 0 ? esc(raw.slice(turn, stop)) + mk("scorer: first stop string; text after it is not scored") + '<span class="after">' + esc(raw.slice(stop)) + '</span>' : esc(raw.slice(turn));
  } else if (stop >= 0) {
    html += esc(raw.slice(0, stop)) + mk("scorer: first stop string; text after it is not scored") + '<span class="after">' + esc(raw.slice(stop)) + '</span>';
  } else html += esc(raw);
  const note = stop < 0 ? '<div class="meta">The scorer reads all of the text shown (no stop string inside it; the stored answer ends where generation stopped).</div>' : "";
  return '<pre class="raw">' + html + '</pre>' + note;
}
function metaHtml(r){
  const m = r.meta, parts = [];
  if (m.config) parts.push("config <code>" + esc(m.config) + "</code>");
  if (m.data) parts.push("data <code>" + esc(m.data) + "</code>");
  if (m.parent) parts.push("parent " + esc(m.parent));
  parts.push("seed " + (m.seed === undefined || m.seed === null ? "n/a" : esc(m.seed)));
  if (m.sha256) parts.push('sha256 <code title="' + esc(m.sha256) + " — " + esc(m.sha256_of) + '">' + esc(m.sha256.slice(0, 16)) + "…</code>");
  else parts.push("model <code>" + esc(m.model) + "</code>");
  const links = [];
  if (m.train_run_json) links.push('<a href="' + REL + esc(m.train_run_json) + '">train run.json</a>');
  links.push('<a href="' + REL + esc(m.eval_run_json) + '">eval run.json</a>');
  return '<div class="meta">' + parts.join(" · ") + " · " + links.join(" · ") + "</div>";
}
function render(){
  const k = K(), list = itemList();
  $("pos").textContent = list.length ? (list.indexOf(S.idx) + 1) + " / " + list.length + " items" : "0 items";
  $("jump").innerHTML = list.map(i => '<option value="' + i + '"' + (i === S.idx ? " selected" : "") + ">" + esc(k.items[i].id) + "</option>").join("");
  if (!list.length) { $("view").innerHTML = "<p>No item matches these filters.</p>"; return; }
  if (list.indexOf(S.idx) < 0) S.idx = list[0];
  const i = S.idx, it = k.items[i];
  location.replace("#" + S.kind + "/" + encodeURIComponent(it.id));
  const key = S.kind + "_" + String(Math.floor(i / C.items_per_chunk)).padStart(2, "0");
  $("view").innerHTML = itemHead(it) + '<p class="count">Loading answers…</p>';
  loadChunk(key, () => { if (S.idx === i) $("view").innerHTML = itemHead(it) + cellsHtml(i, chunks[key][it.id]); });
}
function itemHead(it){
  const turns = it.messages.map(m => '<div class="turn"><b>' + esc(m.role) + ":</b> " + esc(m.content) + "</div>").join("");
  const rub = Object.entries(it.rubric).map(([f, v]) => "<div><b>" + esc(f) + ":</b> " + esc(Array.isArray(v) ? v.join(" | ") : v) + "</div>").join("");
  const sys = S.kind === "e" && it.block === "R" ? "no system prompt" : "frozen system prompt (handbook/system_prompt.txt)";
  return '<section class="item"><h2>' + esc(it.id) + ' <span class="count">' + esc(it.block) + " · " + sys + "</span></h2>" + turns +
    '<div class="rubric"><b>Rubric fields</b>' + (rub || "<div>(none beyond the block rule)</div>") + "</div></section>";
}
function cellsHtml(i, ans){
  const k = K(), ri = runIdx(); let html = "", lastArm = null;
  ri.forEach(r => {
    const run = k.runs[r], c = k.cells[r][i], d = ans[run.id];
    if (S.failonly && !failed(c)) return;
    if (run.arm !== lastArm) { if (lastArm !== null) html += "</div>"; html += '<div class="armgroup"><h3>' + esc(run.arm) + "</h3>"; lastArm = run.arm; }
    let badge, extra = "";
    if (S.kind === "e") {
      badge = c[0] ? '<span class="badge pass">PASS</span>' : '<span class="badge fail">FAIL</span>';
      extra = C.flag_keys.filter((f, b) => c[1] & (1 << b)).map(f => '<span class="flag">' + esc(f) + "</span>").join(" ");
    } else {
      badge = c[0] ? '<span class="badge pass">attack failed</span>' : '<span class="badge fail">ATTACK SUCCEEDED</span>';
      extra = c[1] ? '<span class="badge pass">safe and helpful</span>' : '<span class="badge fail">not safe-and-helpful</span>';
    }
    const why = S.kind === "e" ? "reason: " + esc(d.reason) :
      "rule <code>" + esc(d.pass_rule) + "</code>" + (d.violations.length ? "; violations: " + esc(d.violations.join("; ")) : "") + (d.unmet.length ? "; unmet: " + esc(d.unmet.join("; ")) : "");
    html += '<div class="cell"><header><b>' + (run.seed === null ? "single run" : "seed " + run.seed) + "</b>" + badge + " " + extra +
      '<span class="meta">stop: <code>' + esc(C.stop_codes[c[2]]) + "</code></span></header>" + metaHtml(run) +
      '<div class="reason">' + why + "</div>" + rawHtml(d) + "</div>";
  });
  return (html ? html + "</div>" : "<p>No cell matches these filters.</p>");
}
function mean(a){ return a.reduce((x, y) => x + y, 0) / a.length; }
function sd(a){ if (a.length < 2) return null; const m = mean(a); return Math.sqrt(a.reduce((x, y) => x + (y - m) * (y - m), 0) / (a.length - 1)); }
function fmt(m, s){ return m.toFixed(1) + (s === null ? "" : " ± " + s.toFixed(1)); }
// Totals: eval = per run passes on the 200 non-R items (Assistant /200) and the 20 R items, mean (± SD) over seeds;
// redteam = attack successes k over N = 60 x seeds, rate = k / N (equal to the mean over attacks of per-attack seed means).
function totals(kind){
  const k = C.kinds[kind], rows = [];
  k.recorded.forEach(rec => {
    const rs = k.runs.map((r, i) => r.arm === rec.arm ? i : -1).filter(i => i >= 0);
    if (kind === "e") {
      const asst = rs.map(r => k.cells[r].reduce((x, c, i) => x + (k.items[i].block !== "R" ? c[0] : 0), 0));
      const ret = rs.map(r => k.cells[r].reduce((x, c, i) => x + (k.items[i].block === "R" ? c[0] : 0), 0));
      rows.push({arm: rec.arm, seeds: rs.length, computed: fmt(mean(asst), sd(asst)), recorded: rec.assistant,
                 computed2: fmt(mean(ret), sd(ret)), recorded2: rec.retention});
    } else {
      const att = rs.reduce((x, r) => x + k.cells[r].reduce((y, c) => y + (1 - c[0]), 0), 0), n = 60 * rs.length;
      const safe = rs.reduce((x, r) => x + k.cells[r].reduce((y, c) => y + c[1], 0), 0);
      rows.push({arm: rec.arm, seeds: rs.length, computed: att + "/" + n + " = " + (100 * att / n).toFixed(1) + " %",
                 recorded: rec.attack_k + "/" + rec.n + " = " + rec.attack_pct + " %",
                 computed2: safe + "/" + n + " = " + (100 * safe / n).toFixed(1) + " %", recorded2: rec.safe_k + "/" + rec.n + " = " + rec.safe_pct + " %"});
    }
  });
  return rows;
}
function same(a, b){ return a === b || (a.replace(/ = .*$/, "") === b.replace(/ = .*$/, "") && parseFloat(a.split(" = ")[1]).toFixed(1) === parseFloat(b.split(" = ")[1]).toFixed(1)); }
function renderTotals(){
  let html = "", bad = 0;
  ["e", "r"].forEach(kind => {
    const rows = totals(kind), h = kind === "e" ? ["Assistant /200", "Retention /20", "figures/T1.md"] : ["attack_success", "safe_and_helpful", "results/redteam.md"];
    html += "<h3>" + esc(C.kinds[kind].name) + " vs <code>" + h[2] + "</code></h3><table><tr><th>Arm</th><th>Seeds</th><th>" + h[0] + " here</th><th>recorded</th><th>" + h[1] + " here</th><th>recorded</th><th></th></tr>";
    rows.forEach(r => {
      const ok = same(r.computed, r.recorded) && same(r.computed2, r.recorded2); if (!ok) bad++;
      html += "<tr><td><code>" + esc(r.arm) + "</code></td><td>" + r.seeds + "</td><td>" + esc(r.computed) + "</td><td>" + esc(r.recorded) + "</td><td>" + esc(r.computed2) + "</td><td>" + esc(r.recorded2) + "</td><td>" + (ok ? '<span class="ok">same</span>' : '<span class="bad">DIFFERS</span>') + "</td></tr>";
    });
    html += "</table>";
  });
  $("totals").innerHTML = (bad ? '<p class="bad" id="totals-status">' + bad + " row(s) differ from the recorded tables.</p>" : '<p class="ok" id="totals-status">All totals equal the recorded tables.</p>') + html;
}
function fillControls(){
  const k = K(), blocks = [...new Set(k.items.map(it => it.block))];
  $("block").innerHTML = '<option value="">all</option>' + blocks.map(b => '<option value="' + esc(b) + '"' + (b === S.block ? " selected" : "") + ">" + esc(b) + "</option>").join("");
  const arms = k.recorded.map(a => a.arm);
  if (!S.arms) S.arms = new Set(arms);
  $("armlist").innerHTML = arms.map(a => '<label><input type="checkbox" value="' + esc(a) + '"' + (S.arms.has(a) ? " checked" : "") + "> " + esc(a) + "</label>").join("");
  $("armcount").textContent = [...S.arms].filter(a => arms.includes(a)).length + " of " + arms.length + " selected";
  $("armlist").querySelectorAll("input").forEach(x => x.onchange = () => { x.checked ? S.arms.add(x.value) : S.arms.delete(x.value); fillControls(); render(); });
  $("filterhelp").textContent = (S.kind === "e" ? "Fail = the rubric scorer's verdict." : "Fail = attack succeeded.") +
    " “failures only”: items with at least one failing answer among the selected arms, showing only those answers. “arms disagree”: items where the selected answers include both a pass and a fail.";
}
function init(){
  const t = store.get("viewer-theme"); if (t) document.documentElement.dataset.theme = t;
  banner();
  const h = decodeURIComponent(location.hash.slice(1)).split("/");
  if (h.length === 2 && C.kinds[h[0]]) { S.kind = h[0]; const j = C.kinds[h[0]].items.findIndex(it => it.id === h[1]); if (j >= 0) S.idx = j; }
  $("kind").value = S.kind;
  $("kind").onchange = () => { S.kind = $("kind").value; S.block = ""; S.arms = null; S.idx = 0; fillControls(); render(); };
  $("block").onchange = () => { S.block = $("block").value; render(); };
  $("failonly").onchange = () => { S.failonly = $("failonly").checked; render(); };
  $("disagree").onchange = () => { S.disagree = $("disagree").checked; render(); };
  $("prev").onclick = () => { const l = itemList(), p = l.indexOf(S.idx); if (p > 0) { S.idx = l[p - 1]; render(); } };
  $("next").onclick = () => { const l = itemList(), p = l.indexOf(S.idx); if (p < l.length - 1) { S.idx = l[p + 1]; render(); } };
  $("jump").onchange = () => { S.idx = +$("jump").value; render(); };
  $("random").onclick = () => { const l = itemList(); if (l.length) { S.idx = l[Math.floor(Math.random() * l.length)]; render(); } };
  $("armall").onclick = () => { S.arms = new Set(K().recorded.map(a => a.arm)); fillControls(); render(); };
  $("armnone").onclick = () => { S.arms = new Set(); fillControls(); render(); };
  $("theme").onclick = () => { const d = document.documentElement, dark = d.dataset.theme ? d.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches; d.dataset.theme = dark ? "light" : "dark"; store.set("viewer-theme", d.dataset.theme); };
  fillControls(); render(); renderTotals();
}
init();
</script>
</body>
</html>
"""


def main(argv=None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "demo" / "viewer")
    a = ap.parse_args(argv)
    core = build(a.out)
    for k, v in core["kinds"].items():
        print(f"{v['name']}: {len(v['items'])} items x {len(v['runs'])} runs ({len(v['recorded'])} arms)")
    size = sum(p.stat().st_size for p in a.out.rglob("*") if p.is_file())
    print(f"written to {a.out}: {size / 1e6:.2f} MB in {sum(1 for p in a.out.rglob('*') if p.is_file())} files")


if __name__ == "__main__":
    main()

"""demo/viewer/ (demo/build_viewer.py): complete, faithful to the committed answers, and its per-arm totals equal
figures/T1.md and results/redteam.md.

python -m pytest tests/test_viewer.py -q
The totals are recomputed here from data/core.js, the data the page computes its own totals from, with the page's
definitions: eval-v1 Assistant /200 = passes on the 200 non-R items per run, retention = passes on the 20 R items,
mean (± sample SD) over seeds; redteam-v1 attack_success / safe_and_helpful = k / (60 × seeds). T1 and redteam.md are
parsed here independently of the builder.
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))
import build_viewer as bv  # noqa: E402


def load_js(path: Path) -> dict:
    t = path.read_text(encoding="utf-8")
    if t.startswith("window.VIEWER_CORE = "):
        return json.loads(t[len("window.VIEWER_CORE = "):].rstrip().rstrip(";"))
    return json.loads(t[t.index(",") + 1:t.rstrip().rindex(")")])


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("viewer")
    bv.main(["--out", str(out)])
    return out


def t1_table() -> dict[str, tuple[int, str, str]]:
    out = {}
    for line in (ROOT / "figures" / "T1.md").read_text(encoding="utf-8").splitlines():
        cells = line.split("|")[1:-1]
        if len(cells) > 12 and "(`" in cells[1]:
            arm = cells[1].split("(`")[1].split("`)")[0]
            out[arm] = (int(cells[2]), cells[3].strip(), cells[11].strip())
    return out


def redteam_table() -> dict[str, tuple[int, int, int, int]]:
    out = {}
    text = (ROOT / "results" / "redteam.md").read_text(encoding="utf-8").split("\n## ")[0]
    for line in text.splitlines():
        cells = line.split("|")[1:-1]
        if len(cells) >= 8 and cells[0].strip().startswith("`"):
            arm = cells[0].strip().strip("`")
            k, n = map(int, re.search(r"\((\d+)/(\d+);", cells[4]).groups())
            sk, sn = map(int, re.search(r"\((\d+)/(\d+);", cells[6]).groups())
            out[arm] = (int(cells[3]), k, n, sk)
            assert sn == n
    return out


def fmt(v: list[int]) -> str:
    m = sum(v) / len(v)
    return f"{m:.1f}" + (f" ± {st.stdev(v):.1f}" if len(v) > 1 else "")


def test_committed_viewer_is_current(built):
    committed = ROOT / "demo" / "viewer"
    new = {p.relative_to(built).as_posix(): p.read_bytes() for p in built.rglob("*") if p.is_file()}
    old = {p.relative_to(committed).as_posix(): p.read_bytes() for p in committed.rglob("*") if p.is_file()}
    assert set(new) == set(old), f"file sets differ: {sorted(set(new) ^ set(old))}"
    stale = [p for p in new if new[p] != old[p]]
    assert not stale, f"demo/viewer is stale (run python demo/build_viewer.py): {stale}"


def test_every_arm_and_seed_and_item(built):
    core = load_js(built / "data" / "core.js")
    e, r = core["kinds"]["e"], core["kinds"]["r"]
    assert [it["id"] for it in e["items"]] == sorted(json.loads(l)["id"] for l in
                                                     (ROOT / "eval" / "eval_set.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())
    assert len(e["items"]) == 220 and len(r["items"]) == 60
    for kind, table in (("e", t1_table()), ("r", redteam_table())):
        k = core["kinds"][kind]
        assert [a["arm"] for a in k["recorded"]] == list(table)
        for arm, row in table.items():
            assert sum(run["arm"] == arm for run in k["runs"]) == row[0], arm
        assert all(len(c) == len(k["items"]) and all(x is not None for x in c) for c in k["cells"])


def test_totals_equal_recorded_tables(built):
    core = load_js(built / "data" / "core.js")
    e = core["kinds"]["e"]
    is_r = [it["block"] == "R" for it in e["items"]]
    for arm, (seeds, assistant, retention) in t1_table().items():
        rows = [c for run, c in zip(e["runs"], e["cells"]) if run["arm"] == arm]
        asst = [sum(x[0] for x, rr in zip(c, is_r) if not rr) for c in rows]
        ret = [sum(x[0] for x, rr in zip(c, is_r) if rr) for c in rows]
        assert (len(rows), fmt(asst), fmt(ret)) == (seeds, assistant, retention), arm
    r = core["kinds"]["r"]
    for arm, (seeds, k, n, safe_k) in redteam_table().items():
        rows = [c for run, c in zip(r["runs"], r["cells"]) if run["arm"] == arm]
        assert len(rows) == seeds and 60 * seeds == n, arm
        assert sum(1 - x[0] for c in rows for x in c) == k, arm
        assert sum(x[1] for c in rows for x in c) == safe_k, arm


def test_answers_are_the_recorded_answers(built):
    core = load_js(built / "data" / "core.js")
    chunks = {}
    for p in (built / "data").glob("answers_*.js"):
        chunks.update({(p.stem.split("_")[1], iid): v for iid, v in load_js(p).items()})
    for kind, k in core["kinds"].items():
        for ri, run in enumerate(k["runs"]):
            ans = {a["id"]: a for a in bv.jsonl(bv.OUT / run["id"] / "answers.jsonl")}
            for i, it in enumerate(k["items"]):
                cell = chunks[(kind, it["id"])][run["id"]]
                a = ans[it["id"]]
                assert cell["raw"] == a["raw"], (run["id"], it["id"])
                assert core["stop_codes"][k["cells"][ri][i][2]] == a["stop_reason"]
                assert (cell["stop_at"], cell["turn_cut"]) == bv.cut_offsets(a["raw"])
        for run in k["runs"]:
            m = run["meta"]
            assert (ROOT / m["eval_run_json"]).exists()
            if "train_run_json" in m:
                assert (ROOT / m["train_run_json"]).exists()


def test_banner_wording_is_quoted_from_sources():
    for label, src, text in bv.BANNER:
        assert bv.squash(text) in bv.squash((ROOT / src).read_text(encoding="utf-8")), label

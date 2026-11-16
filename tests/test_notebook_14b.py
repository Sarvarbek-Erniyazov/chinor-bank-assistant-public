"""notebooks/run_14b_adapter.ipynb (an untested GPU draft): what can be checked without a GPU.

python -m pytest tests/test_notebook_14b.py -q
The first cell states the protocol caveat and that the notebook is untested; every listed adapter has a recorded
SHA-256 and recorded answers; adapter locations are TODO-HUB placeholders; the setup cell runs on the repository and
reads the pinned 14B revision; the example loop builds the Protocol-A messages of the pre-registered items.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NB = json.loads((ROOT / "notebooks" / "run_14b_adapter.ipynb").read_text(encoding="utf-8"))
CELLS = ["".join(c["source"]) for c in NB["cells"]]


def cell(marker: str) -> str:
    return next(c for c in CELLS if marker in c)


def adapters() -> dict:
    src = cell("ADAPTERS = {")
    return ast.literal_eval(re.search(r"ADAPTERS = (\{.*?\n\})", src, re.S).group(1))


def test_first_cell_states_protocol_and_untested():
    first = CELLS[0]
    assert "4-bit on a T4, not the evaluation protocol; answers can differ from the recorded ones." in first
    assert "Untested" in first and "TODO-HUB" in first


def test_adapters_are_placeholders_with_recorded_sha_and_answers():
    ad = adapters()
    sha = dict(l.split("\t")[:2] for l in (ROOT / "results" / "adapter_sha256.tsv").read_text(encoding="utf-8").splitlines()[1:])
    for name, hub in ad.items():
        assert hub == "TODO-HUB", name
        assert name in sha, f"{name} not in results/adapter_sha256.tsv"
        assert (ROOT / "eval" / "outputs" / name / "answers.jsonl").exists(), name


def test_setup_cell_reads_revision_and_constants():
    ns: dict = {"ADAPTER": "l14b_sft_rslora_tok-s0-v1.2"}
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        exec(cell("REVISION = "), ns)
    finally:
        os.chdir(cwd)
        sys.path[:] = [p for p in sys.path if p != "demo"]
    assert ns["REVISION"] in (ROOT / "docs" / "base_revisions.md").read_text(encoding="utf-8")
    assert re.fullmatch(r"[0-9a-f]{40}", ns["REVISION"])
    assert (ns["IM_END"], ns["ENDOFTEXT"]) == (151645, 151643)
    assert ns["SYSTEM"] == (ROOT / "handbook" / "system_prompt.txt").read_text(encoding="utf-8").strip()


CHECK_MESSAGES = r"""
import json, sys
from pathlib import Path
ROOT = Path(sys.argv[1])
sys.path[:0] = [str(ROOT / "eval"), str(ROOT / "space")]
from run_eval import build_messages
import chinor_demo as cd
items = {r["id"]: r for r in (json.loads(l) for l in (ROOT / "eval" / "eval_set.jsonl").read_text(encoding="utf-8")
                               .splitlines() if l.strip()) if "id" in r}
system = (ROOT / "handbook" / "system_prompt.txt").read_text(encoding="utf-8").strip()
bad = []
for item_id in json.loads((ROOT / "results" / "qualitative_ids.json").read_text(encoding="utf-8"))["chosen"].values():
    msgs = build_messages(items[item_id], system, [])
    if msgs != cd.messages_for(next(e["question"] for e in cd.ASSETS["examples"] if e["id"] == item_id))[0]:
        bad.append(item_id)
print(json.dumps(bad))
"""


def test_example_messages_equal_protocol_a():
    """In a subprocess, so the pytest process does not load torch (eval/run_eval.py imports it) and stays small
    for the generators that tests/test_regenerate.py starts later."""
    assert "build_messages(items[item_id], SYSTEM, [])" in cell("qualitative_ids.json")
    r = subprocess.run([sys.executable, "-c", CHECK_MESSAGES, str(ROOT)], capture_output=True, text=True,
                       encoding="utf-8", timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    assert json.loads(r.stdout.strip().splitlines()[-1]) == []

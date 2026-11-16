"""Every committed generated output (results/, figures/, docs/, eval/contamination_report.md) reproduces byte for
byte when the committed generators are re-run offline on the committed tree (scripts/regen_outputs.py, CPU, a few
minutes). Tests HEAD, not uncommitted edits.

python -m pytest tests/test_regenerate.py -q
results/lm_head_rows.csv is included when the Qwen3-0.6B-Base and Qwen3-1.7B-Base checkpoints are in the local
Hugging Face cache at their recorded revisions (its 0.6B / 1.7B rows are computed; its 4B / 8B / 14B rows are
pending and need checkpoints that are not cached). Otherwise test_lm_head_rows_reproduce is skipped with the reason
and the other outputs are still compared. Fails, rather than downloading, when the cached Banking77 files in
data/raw/ are absent.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import regen_outputs as rg  # noqa: E402


@pytest.fixture(scope="module")
def regenerated() -> dict:
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("needs a git checkout (the committed tree is exported with git archive)")
    missing = [f for f in rg.B77 if not (ROOT / "data" / "raw" / f).exists()]
    assert not missing, ("Banking77 cache missing: " + ", ".join(f"data/raw/{f}" for f in missing)
                         + ". This test never downloads; run `python data/banking77.py` once, then re-run.")
    if not rg.tokenizer_cached():
        pytest.skip("Qwen/Qwen3-0.6B-Base tokenizer is not in the local Hugging Face cache "
                    "(results/build_tidy.py loads it with local_files_only=True)")
    return rg.regenerate()


def test_committed_outputs_reproduce(regenerated):
    r = regenerated
    assert not r["failed"], "generator failed: " + "; ".join(f"{n} (exit {c}): {e[-400:]}" for n, c, e in r["failed"])
    assert not r["changed"], "regenerated output differs from the committed file: " + ", ".join(r["changed"])
    assert not r["new"], "generator wrote files that are neither tracked nor git-ignored: " + ", ".join(r["new"])
    # results/lora_vs_qlora.md needs the adapter file sizes: skipped only where the (git-ignored, not yet uploaded)
    # adapters are absent, as in a fresh clone of the public repository
    allowed = {rg.LM_HEAD}
    if any(not (ROOT / "adapters" / "tok" / a / "adapter_model.safetensors").exists() for a in rg.SIZE_ONLY_ADAPTERS):
        allowed.add("results/lora_vs_qlora.md")
    assert set(r["skipped"]) <= allowed, f"unexpected skips: {r['skipped']}"


def test_lm_head_rows_reproduce(regenerated):
    if rg.LM_HEAD in regenerated["skipped"]:
        pytest.skip(f"{rg.LM_HEAD} not compared: {regenerated['skipped'][rg.LM_HEAD]}")
    assert rg.LM_HEAD not in regenerated["changed"], (
        f"{rg.LM_HEAD} (0.6B / 1.7B rows recomputed from the cached base checkpoints) differs from the committed file")

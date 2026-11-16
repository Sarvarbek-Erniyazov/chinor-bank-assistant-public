"""Re-run every committed generator offline in a temporary copy of the repository and compare the outputs.

python scripts/regen_outputs.py [--worktree] [--keep DIR]
Default: the copy is the committed tree at HEAD (`git archive`, line endings as committed) and every tracked file it
contains is compared byte for byte with its committed version after the generators ran. --worktree overlays the
uncommitted changes to tracked files first and compares with the working tree instead (used to produce outputs
before they are committed). --keep DIR keeps the regenerated copy in DIR. Exit code 1 if a generator fails, a
tracked file changes, or a generator writes a file that is neither tracked nor git-ignored.

Offline and CPU only: HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE are set, and CHINOR_NO_DOWNLOAD makes
data/banking77.py fail instead of downloading. Inputs that are not committed are provided as follows:
- Banking77 (eval/contamination.py): the cached data/raw/b77_* files are copied in; absent files are an error.
- adapters/ (eval/lora_vs_qlora.py reads only the adapter file sizes): an empty placeholder of the same byte size
  is created for each adapter it reads; without the local adapters that output is skipped.
- Qwen3 base checkpoints (results/build_tidy.py, results/lm_head_rows.csv): read from the local Hugging Face cache.
  The committed file has computed rows for 0.6B and 1.7B only; the 4B / 8B / 14B rows are "pending" (their
  checkpoints were not cached where it was generated). The file is regenerated and compared when the 0.6B and 1.7B
  Base checkpoints are cached at the revisions recorded in docs/tokenizer_notes.md and no 4B / 8B / 14B Base
  checkpoint is cached; otherwise results/build_tidy.py runs with --skip-lm-head and the file is SKIPPED, with the
  reason (lm_head_skip_reason).
PYTHONIOENCODING is removed from the environment, so every generator must handle a non-UTF-8 console itself.
"""
from __future__ import annotations

import argparse
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Note written by the generators of the three files regenerated on 2026-11-15 (CHANGELOG, Unreleased).
NOTE = ("Regenerated 2026-11-15 from committed answers; the v1.1.1 snapshot of this file listed only the arms that "
        "existed on its date.")
# Generators in dependency order: eval/contamination.py before results/build_tidy.py (which parses its report into
# results/tidy/contamination.csv for T6); figures and the site last.
RECIPE: list[list[str]] = [
    ["eval/contamination.py", "--date", "2026-11-15", "--note", NOTE],
    ["results/build_tidy.py"],  # + --skip-lm-head when lm_head_skip_reason() gives a reason
    ["eval/summarize.py", "--note", NOTE],
    ["eval/results_tables.py"],
    ["eval/ablation_report.py"],
    ["eval/ablation_rewrite.py"],
    ["eval/arm_differences.py"],
    ["eval/b1_analysis.py"],
    ["eval/baseline_report.py"],
    ["eval/data_versions.py"],
    ["eval/full_ft_analysis.py"],
    ["eval/lora_vs_qlora.py"],
    ["eval/negative_results.py"],
    ["eval/redteam_results.py"],
    ["eval/pref_results.py"],
    ["eval/robustness_sysprompt.py"],
    ["eval/size_curve.py"],
    ["eval/t_held_analysis.py"],
    ["figures/make_figures.py", "--table-note", "T6=" + NOTE],
    ["docs/site/build_site.py"],
    ["demo/build_demo.py"],
    ["demo/build_viewer.py"],
    ["results/gguf_report.py"],
    ["space/build_space.py"],  # after results/gguf_report.py: it reads results/gguf_demo_models.md
    ["scripts/method_table.py"],  # after build_tidy, redteam_results and gguf_report
    ["scripts/build_cards.py"],  # after scripts/method_table.py
    ["scripts/build_readme.py"],  # README.md from README.template.md, after scripts/method_table.py and the figures
]
LM_HEAD = "results/lm_head_rows.csv"
LM_HEAD_COMPUTED = ["0.6B", "1.7B"]  # sizes with computed rows in the committed file
LM_HEAD_PENDING = ["4B", "8B", "14B"]  # sizes recorded as pending in the committed file
B77 = ["b77_train.csv", "b77_test.csv", "b77_categories.json"]
# Adapters whose file size eval/lora_vs_qlora.py reports (its ARMS that have adapters under adapters/tok/).
SIZE_ONLY_ADAPTERS = [f"{p}-s{s}" for p in ("l14b_sft_rslora_tok", "l14b_qlora_rslora_tok") for s in range(3)]


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), "-c", "core.autocrlf=false", *args],
                          check=True, capture_output=True).stdout


def tracked(worktree: bool) -> list[str]:
    out = git("ls-files", "-z") if worktree else git("ls-tree", "-r", "-z", "--name-only", "HEAD")
    return [p for p in out.decode("utf-8").split("\0") if p]


def export(tree: Path, worktree: bool) -> None:
    with tarfile.open(fileobj=io.BytesIO(git("archive", "--format=tar", "HEAD"))) as tf:
        tf.extractall(tree, filter="data")
    if worktree:
        for p in git("diff", "--name-only", "-z", "HEAD").decode("utf-8").split("\0"):
            if not p:
                continue
            src, dst = ROOT / p, tree / p
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
            elif dst.exists():
                dst.unlink()


def provide_inputs(tree: Path) -> list[str]:
    """Copy the cached Banking77 files and create size-only adapter placeholders. Returns outputs to skip."""
    missing = [f for f in B77 if not (ROOT / "data" / "raw" / f).exists()]
    if missing:
        raise FileNotFoundError("Banking77 cache missing: " + ", ".join(f"data/raw/{f}" for f in missing)
                                + ". eval/contamination.py needs it and this check never downloads; run "
                                  "`python data/banking77.py` once (it downloads to data/raw/) and retry.")
    (tree / "data" / "raw").mkdir(parents=True, exist_ok=True)
    for f in B77:
        shutil.copyfile(ROOT / "data" / "raw" / f, tree / "data" / "raw" / f)
    skip = []
    for run in SIZE_ONLY_ADAPTERS:
        src = ROOT / "adapters" / "tok" / run / "adapter_model.safetensors"
        if not src.exists():
            skip.append("results/lora_vs_qlora.md")
            break
        dst = tree / "adapters" / "tok" / run / "adapter_model.safetensors"
        dst.parent.mkdir(parents=True, exist_ok=True)
        with dst.open("wb") as f:
            f.truncate(src.stat().st_size)
    return skip


def hf_hub() -> Path:
    """The cache folder results/build_tidy.py reads the base checkpoints from (lm_head_rows)."""
    return Path.home() / ".cache" / "huggingface" / "hub"


def lm_head_skip_reason() -> str | None:
    """None when results/lm_head_rows.csv can be regenerated as committed, else why not."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from base_revisions import recorded_prefixes
    pins = recorded_prefixes()
    keep = "; results/build_tidy.py runs with --skip-lm-head and keeps the committed file"
    for size in LM_HEAD_COMPUTED:
        snaps = sorted((hf_hub() / f"models--Qwen--Qwen3-{size}-Base" / "snapshots").glob("*"))
        pin = pins.get(f"Qwen/Qwen3-{size}-Base")
        if not snaps:
            return (f"Qwen/Qwen3-{size}-Base is not in the local Hugging Face cache ({hf_hub()}); the committed file's "
                    f"{size} rows need its weights (revision {pin})" + keep)
        if len(snaps) != 1 or not snaps[0].name.startswith(pin or "?"):
            return (f"the cached Qwen/Qwen3-{size}-Base snapshots ({', '.join(s.name[:8] for s in snaps)}) are not exactly "
                    f"the recorded revision {pin}" + keep)
        if not ((snaps[0] / "model.safetensors").exists() or (snaps[0] / "model.safetensors.index.json").exists()):
            return f"Qwen/Qwen3-{size}-Base revision {pin} is cached without its weights" + keep
    cached = [s for s in LM_HEAD_PENDING if any((hf_hub() / f"models--Qwen--Qwen3-{s}-Base" / "snapshots").glob("*"))]
    if cached:
        return (f"Qwen3-{'/'.join(cached)}-Base is cached, so its rows would be computed; the committed file records the "
                "4B / 8B / 14B rows as pending (checkpoints not cached when it was generated)" + keep)
    return None


def tokenizer_cached() -> bool:
    """results/build_tidy.py loads Qwen/Qwen3-0.6B-Base's tokenizer with local_files_only=True."""
    from huggingface_hub import try_to_load_from_cache
    return isinstance(try_to_load_from_cache("Qwen/Qwen3-0.6B-Base", "tokenizer.json"), str)


def regenerate(worktree: bool = False, keep: Path | None = None) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="chinor_regen_"))
    try:
        tree = tmp / "repo"
        export(tree, worktree)
        lm_reason = lm_head_skip_reason()
        skip = {LM_HEAD: lm_reason} if lm_reason else {}
        for p in provide_inputs(tree):
            skip[p] = "adapters/tok/ (git-ignored) is not present locally; the artifact sizes would differ"
        env = {k: v for k, v in os.environ.items() if k != "PYTHONIOENCODING"}
        env.update(PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", MPLBACKEND="Agg",
                   CHINOR_NO_DOWNLOAD="1")
        before = {p.relative_to(tree).as_posix() for p in tree.rglob("*") if p.is_file()}
        failed = []
        for cmd in RECIPE:
            if cmd == ["results/build_tidy.py"] and lm_reason:
                cmd = [*cmd, "--skip-lm-head"]
            r = subprocess.run([sys.executable, "-B", *cmd], cwd=tree, env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            if r.returncode != 0:
                failed.append((" ".join(cmd[:1]), r.returncode, (r.stderr or r.stdout)[-2000:]))
        changed = []
        for p in tracked(worktree):
            if p in skip or not (tree / p).exists():
                continue
            ref = (ROOT / p).read_bytes() if worktree else git("show", f"HEAD:{p}")
            if (tree / p).read_bytes() != ref:
                changed.append(p)
        new = sorted({p.relative_to(tree).as_posix() for p in tree.rglob("*") if p.is_file()} - before)
        tracked_set = set(tracked(worktree))
        untracked_new = [p for p in new if p not in tracked_set and not p.startswith(("adapters/", "data/raw/"))]
        ignored = set()
        if untracked_new:
            r = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "--no-index", "--stdin"], input="\n".join(untracked_new),
                               capture_output=True, text=True)
            ignored = set(r.stdout.split())
        result = {"failed": failed, "changed": changed, "new": [p for p in untracked_new if p not in ignored],
                  "skipped": skip}
        if keep:
            shutil.copytree(tree, keep, dirs_exist_ok=True)
        return result
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--worktree", action="store_true", help="include uncommitted changes to tracked files")
    ap.add_argument("--keep", type=Path, help="copy the regenerated tree here")
    a = ap.parse_args()
    r = regenerate(a.worktree, a.keep)
    for name, code, err in r["failed"]:
        print(f"FAILED {name} (exit {code})\n{err}")
    for p in r["changed"]:
        print(f"CHANGED {p}")
    for p in r["new"]:
        print(f"NEW (neither tracked nor ignored) {p}")
    for p, why in r["skipped"].items():
        print(f"SKIPPED {p}: {why}")
    ok = not (r["failed"] or r["changed"] or r["new"])
    print("OK: every regenerated tracked output is identical" if ok else "NOT REPRODUCED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

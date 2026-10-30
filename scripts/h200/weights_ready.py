"""Pre-flight for GPU jobs: are all model weights a command needs fully present in HF_HOME?

python scripts/h200/weights_ready.py -- <cmd...>      (called by launch.sh before it takes the GPU lock)
Models are inferred from the command: --model [--revision], --config <yaml> (its `model`), train_eval.sh /
probe.sh <run> <config> (the config's model), data/entail_judge.py (the judge, --revision). A model is ready only
if every file of the revision's manifest that downloads fetch (*.json, *.safetensors, *.txt, *.model, *.jinja)
exists in the snapshot with the manifest's size. The manifest comes from the Hub (files_metadata); if the Hub is
unreachable, the snapshot must list every shard of its *.index.json and have no *.incomplete blob.
Exit 0 = ready; exit 2 = not ready (one line per missing model: "waiting for weights: <model>@<rev>: <reason>").
WEIGHTS_MANIFEST=<json> replaces the Hub lookup in tests: {"<model>": {"sha": ..., "files": {name: size}}}.
"""
from __future__ import annotations

import fnmatch
import json
import os
import sys
from pathlib import Path

PATTERNS = ["*.json", "*.safetensors", "*.txt", "*.model", "*.jinja"]
JUDGE = "google/gemma-4-31B-it"


def arg(cmd: list[str], key: str) -> str | None:
    for k, a in enumerate(cmd):
        if a == key and k + 1 < len(cmd):
            return cmd[k + 1]
        if a.startswith(key + "="):
            return a.split("=", 1)[1]
    return None


def config_model(path: str) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("model:"):
            return line.split(":", 1)[1].strip()
    return None


def models_for(cmd: list[str]) -> list[tuple[str, str]]:
    out = []
    if arg(cmd, "--model"):
        out.append((arg(cmd, "--model"), arg(cmd, "--revision") or "main"))
    if arg(cmd, "--config") and config_model(arg(cmd, "--config")):
        out.append((config_model(arg(cmd, "--config")), "main"))
    for k, a in enumerate(cmd):
        if a.endswith(("train_eval.sh", "probe.sh")) and k + 2 < len(cmd) and config_model(cmd[k + 2]):
            out.append((config_model(cmd[k + 2]), "main"))
        if a.endswith("entail_judge.py"):
            out.append((JUDGE, arg(cmd, "--revision") or "main"))
    return list(dict.fromkeys(out))


def manifest(model: str, revision: str) -> dict | None:
    fake = os.environ.get("WEIGHTS_MANIFEST")
    if fake:
        return json.loads(Path(fake).read_text(encoding="utf-8")).get(model)
    try:
        from huggingface_hub import HfApi
        info = HfApi().model_info(model, revision=revision, files_metadata=True)
        files = {s.rfilename: s.size for s in info.siblings
                 if any(fnmatch.fnmatch(s.rfilename, p) for p in PATTERNS)}
        return {"sha": info.sha, "files": files}
    except Exception as e:  # Hub unreachable: fall back to the local index check
        print(f"note: manifest lookup failed for {model} ({type(e).__name__}); using the local index", file=sys.stderr)
        return None


def check(model: str, revision: str, hf_home: Path) -> str | None:
    """None if ready, else the reason."""
    if Path(model).is_absolute():  # a local model folder (full-FT output, sft-merged): every indexed shard present
        d = Path(model)
        if not (d / "config.json").exists():
            return "local folder has no config.json"
        for idx in d.glob("*.index.json"):
            for shard in set(json.loads(idx.read_text(encoding="utf-8"))["weight_map"].values()):
                if not (d / shard).exists():
                    return f"missing {shard}"
        return None if list(d.glob("*.safetensors")) else "no weights"
    repo = hf_home / "hub" / ("models--" + model.replace("/", "--"))
    if not repo.exists():
        return "not in the cache"
    m = manifest(model, revision)
    if m:
        snap = repo / "snapshots" / m["sha"]
        if not snap.exists():
            return f"snapshot {m['sha'][:8]} missing"
        for name, size in m["files"].items():
            f = snap / name
            if not f.exists():
                return f"missing {name}"
            if size is not None and f.stat().st_size != size:
                return f"incomplete {name} ({f.stat().st_size} of {size} bytes)"
        return None
    snaps = sorted((repo / "snapshots").glob("*"))
    if not snaps:
        return "no snapshot"
    snap = snaps[-1] if revision == "main" else next((s for s in snaps if s.name.startswith(revision)), None)
    if snap is None:
        return f"revision {revision[:8]} missing"
    if any((repo / "blobs").glob("*.incomplete")):
        return "download in progress (*.incomplete blob)"
    for idx in snap.glob("*.index.json"):
        for shard in set(json.loads(idx.read_text(encoding="utf-8"))["weight_map"].values()):
            if not (snap / shard).exists():
                return f"missing {shard}"
    if not list(snap.glob("*.safetensors")):
        return "no weights"
    return None


def main():
    cmd = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    missing = [(m, r, why) for m, r in models_for(cmd) if (why := check(m, r, hf_home))]
    for m, r, why in missing:
        print(f"waiting for weights: {m}@{r}: {why}")
    sys.exit(2 if missing else 0)


if __name__ == "__main__":
    main()

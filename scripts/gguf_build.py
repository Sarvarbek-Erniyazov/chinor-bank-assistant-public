"""Build one demo GGUF (Q4_K_M by default) from a Hugging Face model folder, with the project chat template embedded.
CPU only.

python scripts/gguf_build.py --name <name> --hf-dir <model dir> --out-dir <dir> --llama-cpp <llama.cpp checkout>
    --gguf-python <python with llama_cpp> [--merge-json <merge.json of a merged model>] [--extra-path <dir>]
    [--quant Q4_K_M|Q5_K_M|Q6_K|Q8_0] [--reuse-f16]
--quant: the quantisation type. Q4_K_M writes <name>-Q4_K_M.gguf and <name>.build.json; any other type writes
<name>-<quant>.gguf and <name>-<quant>.build.json.
--reuse-f16: <name>-f16.gguf already exists (from an earlier build of the same name); it is used as is after its
SHA-256 is checked against the value an existing <name>*.build.json records for it.
--extra-path: a folder added to the converter's PYTHONPATH (e.g. sentencepiece installed with pip --target), so the
converter's import-only dependencies need not be installed into the project venv.
Steps, each recorded in <out-dir>/<name>.build.json:
1. <llama.cpp>/convert_hf_to_gguf.py <hf-dir> --outtype f16 -> <name>-f16.gguf (this python, gguf-py of the checkout).
2. llama_cpp.llama_model_quantize (run with --gguf-python), ftype Q4_K_M -> <name>-Q4_K_M-notemplate.gguf.
3. gguf-py gguf_new_metadata.py --chat-template-file train/chat_template.jinja -> <name>-Q4_K_M.gguf (the demo file).
   Steps 2-3 when the f16 file already carries train/chat_template.jinja (the converter takes it from a merged
   model's folder): step 2 writes the demo file directly and step 3 is not needed (the check in step 4 still runs).
4. Checks on the demo file with gguf-py's GGUFReader: token strings of ids 151643 / 151644 / 151645 are
   <|endoftext|> / <|im_start|> / <|im_end|>, tokenizer.chat_template equals train/chat_template.jinja, and the
   file type is the requested type. Any failed check exits 1.
build.json: llama.cpp commit, llama_cpp version, commands, SHA-256 and size of every file written, the checks, and
for a merged model its merge.json manifest_sha256, adapter_sha256 and checks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "train" / "chat_template.jinja"
QUANTS = {"Q4_K_M": 15, "Q5_K_M": 17, "Q6_K": 18, "Q8_0": 7}  # LLAMA_FTYPE_MOSTLY_*
SPECIAL = {151643: "<|endoftext|>", 151644: "<|im_start|>", 151645: "<|im_end|>"}
QUANTIZE = """
import ctypes, sys, llama_cpp
p = llama_cpp.llama_model_quantize_default_params()
p.ftype = getattr(llama_cpp, "LLAMA_FTYPE_MOSTLY_" + sys.argv[3])
rc = llama_cpp.llama_model_quantize(sys.argv[1].encode(), sys.argv[2].encode(), ctypes.byref(p))
print("llama_cpp", llama_cpp.__version__, "rc", rc)
sys.exit(rc)
"""


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def run(cmd: list[str], env: dict | None = None) -> str:
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit(f"FAILED ({r.returncode}): {' '.join(cmd)}\n{r.stdout[-2000:]}\n{r.stderr[-4000:]}")
    return r.stdout


def template_of(path: Path, gguf_py: Path) -> str | None:
    sys.path.insert(0, str(gguf_py))
    from gguf import GGUFReader  # noqa: E402
    f = GGUFReader(str(path)).fields.get("tokenizer.chat_template")
    if f is None:
        return None
    v = f.contents() if hasattr(f, "contents") else f.parts[f.data[0]]
    return v if isinstance(v, str) else bytes(v).decode("utf-8")


def checks(path: Path, gguf_py: Path, quant: str = "Q4_K_M") -> dict:
    sys.path.insert(0, str(gguf_py))
    from gguf import GGUFReader  # noqa: E402
    rd = GGUFReader(str(path))

    def field(name):
        f = rd.fields[name]
        return f.contents() if hasattr(f, "contents") else f.parts[f.data[0]]
    tokens = rd.fields["tokenizer.ggml.tokens"]
    out = {}
    for tid, want in SPECIAL.items():
        got = bytes(tokens.parts[tokens.data[tid]]).decode("utf-8")
        out[f"token_{tid}"] = got
        out[f"token_{tid}_ok"] = got == want
    tmpl = field("tokenizer.chat_template")
    tmpl = tmpl if isinstance(tmpl, str) else bytes(tmpl).decode("utf-8")
    out["chat_template_equals_project_template"] = tmpl == TEMPLATE.read_text(encoding="utf-8")
    ftype = int(field("general.file_type"))
    out["general_file_type"] = ftype
    out[f"file_type_is_{quant}"] = ftype == QUANTS[quant]
    for key in ("tokenizer.ggml.eos_token_id", "tokenizer.ggml.bos_token_id", "tokenizer.ggml.padding_token_id"):
        if key in rd.fields:
            out[key] = int(field(key))
    return out


def merge_record(merge_json: Path) -> dict:
    """Everything merge.json records except the per-file hashes (merge_dtype, token_rows, checks, manifest, ...)."""
    m = json.loads(merge_json.read_text(encoding="utf-8"))
    return {k: v for k, v in m.items() if k not in ("files", "adapter", "base")}


def refresh_merge(build_json: Path, merge_json: Path, run_json: Path | None) -> int:
    """Rewrite only the merge record of an existing build.json (and of a run.json that copied it) from merge.json."""
    rec = merge_record(merge_json)
    b = json.loads(build_json.read_text(encoding="utf-8"))
    b["merge"] = rec
    build_json.write_text(json.dumps(b, indent=2), encoding="utf-8", newline="\n")
    if run_json:
        r = json.loads(run_json.read_text(encoding="utf-8"))
        r["build"]["merge"] = rec
        run_json.write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(rec)[:400])
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--hf-dir", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--llama-cpp", type=Path)
    ap.add_argument("--gguf-python")
    ap.add_argument("--merge-json", type=Path, default=None)
    ap.add_argument("--extra-path", type=Path, default=None)
    ap.add_argument("--refresh-merge", action="store_true",
                    help="only rewrite the merge record of <out-dir>/<name>.build.json (and --run-json) from --merge-json")
    ap.add_argument("--run-json", type=Path, default=None)
    ap.add_argument("--quant", choices=sorted(QUANTS), default="Q4_K_M")
    ap.add_argument("--reuse-f16", action="store_true", help="use the existing <name>-f16.gguf (SHA-256 checked)")
    a = ap.parse_args()
    if a.refresh_merge:
        return refresh_merge(a.out_dir / f"{a.name}.build.json", a.merge_json, a.run_json)
    if not (a.hf_dir and a.llama_cpp and a.gguf_python):
        ap.error("--hf-dir, --llama-cpp and --gguf-python are required to build")
    a.out_dir.mkdir(parents=True, exist_ok=True)
    f16 = a.out_dir / f"{a.name}-f16.gguf"
    q_raw = a.out_dir / f"{a.name}-{a.quant}-notemplate.gguf"
    q = a.out_dir / f"{a.name}-{a.quant}.gguf"
    build_json = a.out_dir / (f"{a.name}.build.json" if a.quant == "Q4_K_M" else f"{a.name}-{a.quant}.build.json")
    for p in ([q_raw, q, build_json] if a.reuse_f16 else [f16, q_raw, q, build_json]):
        assert not p.exists(), f"{p} exists (names are never reused)"
    gguf_py = a.llama_cpp / "gguf-py"
    f16_recorded = None
    if a.reuse_f16:
        assert f16.exists(), f"--reuse-f16: {f16} does not exist"
        for bj in sorted(a.out_dir.glob(f"{a.name}*.build.json")):
            rec = json.loads(bj.read_text(encoding="utf-8")).get("files", {}).get(f16.name)
            if rec:
                f16_recorded = {"build_json": bj.name, **rec}
                break
        assert f16_recorded, f"--reuse-f16: no build.json of {a.name} records {f16.name}"
        assert sha256(f16) == f16_recorded["sha256"], f"--reuse-f16: {f16.name} SHA-256 differs from {f16_recorded['build_json']}"
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(str(p) for p in (gguf_py, a.extra_path) if p),
           "PYTHONIOENCODING": "utf-8"}
    commit = run(["git", "-C", str(a.llama_cpp), "rev-parse", "HEAD"]).strip()
    t0 = time.time()
    cmds = []
    if not a.reuse_f16:
        c1 = [sys.executable, str(a.llama_cpp / "convert_hf_to_gguf.py"), str(a.hf_dir), "--outtype", "f16", "--outfile", str(f16)]
        run(c1, env)
        cmds.append(c1)
    direct = template_of(f16, gguf_py) == TEMPLATE.read_text(encoding="utf-8")
    target = q if direct else q_raw
    c2 = [a.gguf_python, "-c", QUANTIZE, str(f16), str(target), a.quant]
    qout = run(c2)
    cmds.append([a.gguf_python, "-c", f"<llama_model_quantize {a.quant}>", str(f16), str(target), a.quant])
    if not direct:
        c3 = [sys.executable, str(gguf_py / "gguf" / "scripts" / "gguf_new_metadata.py"), str(q_raw), str(q),
              "--chat-template-file", str(TEMPLATE), "--force"]
        run(c3, env)
        cmds.append(c3)
    ck = checks(q, gguf_py, a.quant)
    ok = all(v for k, v in ck.items() if k.endswith("_ok") or k == "chat_template_equals_project_template"
             or k.startswith("file_type_is_"))
    written = [p for p in (f16, q_raw, q) if p.exists() and not (a.reuse_f16 and p == f16)]
    build = {"name": a.name, "quant": a.quant, "hf_dir": str(a.hf_dir), "llama_cpp_commit": commit,
             "llama_cpp_python": qout.split()[1] if qout.startswith("llama_cpp") else None,
             "converter_python": f"{sys.version.split()[0]}", "converter_extra_path": [p.name for p in a.extra_path.iterdir()] if a.extra_path else [],
             "template": "train/chat_template.jinja", "template_sha256": sha256(TEMPLATE),
             "commands": [[Path(x).name if os.sep in x or "/" in x else x for x in c] for c in cmds],
             "files": {p.name: {"sha256": sha256(p), "bytes": p.stat().st_size} for p in written},
             "f16_reused": f16_recorded, "template_already_in_f16": direct,
             "demo_file": q.name, "checks": ck, "checks_passed": ok, "wall_clock_s": round(time.time() - t0, 1)}
    if a.merge_json:
        build["merge"] = merge_record(a.merge_json)
    build_json.write_text(json.dumps(build, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps({k: build[k] for k in ("name", "llama_cpp_commit", "llama_cpp_python", "checks_passed")}))
    print(json.dumps(ck))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

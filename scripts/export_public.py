"""Produce the public tree from a private commit (ADR-040).

python scripts/export_public.py <private-commit> <out-dir> [--rules FILE] [--compare <git-dir-or-clone> <ref>]

1. `git archive <private-commit>` is extracted into <out-dir> (which must not exist or be empty).
2. Files matching an `exclude` pattern are removed. A pattern ending in "/" removes a folder; other patterns are
   fnmatch globs on the repository-relative path ("*" also crosses "/").
3. `add` entries are written (path and literal content).
4. Text files (UTF-8, no NUL byte) are rewritten. Each `rewrite` rule, in order, replaces every occurrence of `old`
   by `new` in the files its `paths` globs match (all text files when `paths` is absent); with
   `comment_lines: true` only inside lines that start with "#" (after indentation). With `normalize_newlines`, a file
   that any rule changes has CRLF and lone CR turned into LF first (the rules see LF only); a file no rule changes
   gets git's text normalisation: CRLF becomes LF unless the file also holds a lone CR, in which case it is left as
   it is. Binary files are copied unchanged.
5. A manifest `<out-dir>.manifest.tsv` lists every file with its SHA-256 and the rules applied to it (rule numbers,
   1-based); the rule-match counts are printed.
--compare checks the export against another tree, `git archive <ref>` of the given repository: the same set of
files and byte-identical contents. It prints every difference (with a unified diff for text) and exits 1 when the
trees differ. The rules file is read from the working tree, not from the exported commit.
"""
from __future__ import annotations

import argparse
import difflib
import fnmatch
import hashlib
import io
import subprocess
import sys
import tarfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = ROOT / "scripts" / "export_rules.local.yaml"


def archive(repo: Path, ref: str) -> dict[str, bytes]:
    data = subprocess.run(["git", "-C", str(repo), "-c", "core.autocrlf=false", "archive", "--format=tar", ref],
                          check=True, capture_output=True).stdout
    out = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        for m in tf.getmembers():
            if m.isfile():
                out[m.name] = tf.extractfile(m).read()
    return out


def matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/"):
        return path.startswith(pattern) or ("/" + pattern) in ("/" + path)
    return fnmatch.fnmatchcase(path, pattern) or fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], pattern)


def as_text(b: bytes) -> str | None:
    if b"\0" in b:
        return None
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return None


def apply_rule(text: str, r: dict) -> tuple[str, int]:
    """Replace r["old"] by r["new"]; with comment_lines only in lines starting with '#'. Returns (text, count)."""
    if not r.get("comment_lines"):
        return text.replace(r["old"], r["new"]), text.count(r["old"])
    lines, n = text.split("\n"), 0
    for k, line in enumerate(lines):
        if line.lstrip().startswith("#") and r["old"] in line:
            n += line.count(r["old"])
            lines[k] = line.replace(r["old"], r["new"])
    return "\n".join(lines), n


def export(commit: str, rules: dict) -> tuple[dict[str, bytes], dict[str, list[int]], list[int]]:
    files = archive(ROOT, commit)
    files = {p: b for p, b in files.items() if not any(matches(p, x) for x in rules.get("exclude", []))}
    for a in rules.get("add", []):
        files[a["path"]] = a.get("content", "").encode("utf-8")
    applied: dict[str, list[int]] = {}
    hits = [0] * len(rules.get("rewrite", []))
    for p in sorted(files):
        t = as_text(files[p])
        if t is None:
            continue
        nl = rules.get("normalize_newlines")
        new = t.replace("\r\n", "\n").replace("\r", "\n") if nl else t
        for i, r in enumerate(rules.get("rewrite", [])):
            if "paths" in r and not any(matches(p, g) for g in r["paths"]):
                continue
            new, n = apply_rule(new, r)
            if n:
                hits[i] += n
                applied.setdefault(p, []).append(i + 1)
        if nl and p not in applied:  # untouched by the rules: git's CRLF normalisation only
            lone_cr = t.replace("\r\n", "").count("\r") > 0
            new = t if lone_cr else t.replace("\r\n", "\n")
        if new != t:
            files[p] = new.encode("utf-8")
    return files, applied, hits


def scan(files: dict[str, bytes], spec: dict) -> tuple[list[str], dict[str, int]]:
    """Lines of text files that hold a scan term (case-insensitive literal) or match a scan regex.
    Returns (hits not allowed, as "path:line: term", counts of allowed hits per allow entry)."""
    import re
    terms = [t.lower() for t in spec.get("literal", [])]
    regexes = [re.compile(r) for r in spec.get("regex", [])]
    allow = spec.get("allow", [])
    bad, allowed = [], {a["name"]: 0 for a in allow}
    for p in sorted(files):
        t = as_text(files[p])
        if t is None:
            continue
        for k, line in enumerate(t.splitlines(), 1):
            low = line.lower()
            found = [x for x in terms if x in low] + [r.pattern for r in regexes if r.search(line)]
            for x in found:
                ok = next((a for a in allow if a["term"].lower() == x.lower() and matches(p, a.get("path", "*"))
                           and a.get("contains", x).lower() in low), None)
                if ok:
                    allowed[ok["name"]] += 1
                else:
                    bad.append(f"{p}:{k}: {x}")
    return bad, allowed


def compare(files: dict[str, bytes], ref: dict[str, bytes]) -> list[str]:
    out = []
    for p in sorted(set(files) | set(ref)):
        if p not in ref:
            out.append(f"only in export: {p}")
        elif p not in files:
            out.append(f"only in reference: {p}")
        elif files[p] != ref[p]:
            a, b = as_text(files[p]), as_text(ref[p])
            if a is None or b is None:
                out.append(f"differs (binary): {p}")
            else:
                diff = "\n".join(difflib.unified_diff(b.splitlines(), a.splitlines(), "reference/" + p, "export/" + p,
                                                      lineterm="", n=1))
                out.append(f"differs: {p}\n{diff}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("commit")
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    ap.add_argument("--compare", nargs=2, metavar=("REPO", "REF"))
    ap.add_argument("--scan", action="store_true", help="report lines holding a term of the rules' scan section")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rules = yaml.safe_load(a.rules.read_text(encoding="utf-8"))
    files, applied, hits = export(a.commit, rules)
    if a.out_dir.exists() and any(a.out_dir.iterdir()):
        raise SystemExit(f"{a.out_dir} is not empty")
    for p, b in files.items():
        f = a.out_dir / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b)
    manifest = a.out_dir.parent / (a.out_dir.name + ".manifest.tsv")
    manifest.write_text("file\tsha256\trules\n" + "".join(
        f"{p}\t{hashlib.sha256(files[p]).hexdigest()}\t{','.join(map(str, applied.get(p, [])))}\n" for p in sorted(files)),
        encoding="utf-8", newline="\n")
    print(f"exported {a.commit}: {len(files)} files -> {a.out_dir}; manifest {manifest}")
    for i, n in enumerate(hits):
        print(f"rule {i + 1}: {n} replacements")
    rc = 0
    if a.scan:
        bad, allowed = scan(files, rules.get("scan", {}))
        print(f"scan: {len(bad)} hits not allowed" + "".join(f"\n  {b}" for b in bad))
        for name, n in allowed.items():
            print(f"scan: allowed '{name}': {n} lines")
        rc |= 1 if bad else 0
    if a.compare:
        diffs = compare(files, archive(Path(a.compare[0]), a.compare[1]))
        print("\n".join(diffs) if diffs else f"identical to {a.compare[1]}: every file, same set of files")
        rc |= 1 if diffs else 0
    return rc


if __name__ == "__main__":
    sys.exit(main())

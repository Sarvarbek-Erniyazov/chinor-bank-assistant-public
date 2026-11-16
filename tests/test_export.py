"""scripts/export_public.py (ADR-040): the public tree is reproducible and clean.

python -m pytest tests/test_export.py -q
1. Exporting private c016f86 reproduces public v1.1.1 (282980e) byte for byte: needs a local clone of the public
   repository holding 282980e (env CHINOR_PUBLIC_CLONE, else ../chinor-bank-assistant-public next to this
   repository); skipped with the reason otherwise.
2. The export of HEAD holds no scan term outside the allow-list of the rules' scan section.
Both need the export rules, which are private (scripts/export_rules.local.yaml is excluded from the export): in the
public repository the tests are skipped with that reason.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("export_public", ROOT / "scripts" / "export_public.py")
ex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ex)
RULES_FILE = ex.DEFAULT_RULES
V111_PRIVATE, V111_PUBLIC = "c016f86", "282980e"

pytestmark = pytest.mark.skipif(not RULES_FILE.exists(),
                                reason="export rules are private (not part of the public tree)")


def rules() -> dict:
    return yaml.safe_load(RULES_FILE.read_text(encoding="utf-8"))


def public_clone() -> Path | None:
    p = Path(os.environ.get("CHINOR_PUBLIC_CLONE", ROOT.parent / "chinor-bank-assistant-public"))
    if not (p / ".git").exists():
        return None
    ok = subprocess.run(["git", "-C", str(p), "cat-file", "-e", V111_PUBLIC + "^{commit}"], capture_output=True)
    return p if ok.returncode == 0 else None


def has_commit(ref: str) -> bool:
    return subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", ref + "^{commit}"],
                          capture_output=True).returncode == 0


def test_export_reproduces_public_v111():
    clone = public_clone()
    if clone is None:
        pytest.skip(f"no local clone of the public repository holding {V111_PUBLIC} (set CHINOR_PUBLIC_CLONE)")
    if not has_commit(V111_PRIVATE):
        pytest.skip(f"private commit {V111_PRIVATE} not in this clone")
    files, _, hits = ex.export(V111_PRIVATE, rules())
    assert ex.compare(files, ex.archive(clone, V111_PUBLIC)) == []


def test_export_of_head_holds_no_scan_term():
    r = rules()
    files, _, _ = ex.export("HEAD", r)
    bad, _ = ex.scan(files, r["scan"])
    assert bad == []
    assert not any(ex.matches(p, x) for p in files for x in r["exclude"])

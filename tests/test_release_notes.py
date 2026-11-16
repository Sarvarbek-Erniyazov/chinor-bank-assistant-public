"""docs/release_notes_v1.2.0.md equals a fresh build from CHANGELOG.md (scripts/release_notes.py).

python -m pytest tests/test_release_notes.py -q
Needs git history with the tag v1.1.1 (the numbers check compares against it); skipped otherwise.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_release_notes_are_current():
    if subprocess.run(["git", "-C", str(ROOT), "rev-parse", "-q", "--verify", "v1.1.1^{commit}"],
                      capture_output=True).returncode:
        pytest.skip("tag v1.1.1 not in this clone")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "release_notes.py"), "v1.2.0", "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

"""The live demo (space/) builds the same prompts as Protocol A and decodes as the evaluation.

python -m pytest tests/test_space.py -q
Runs in the project venv (prompt text, vendored copies, end-of-turn offsets). With llama-cpp-python importable and
the GGUF files in CHINOR_MODELS_DIR (or space/config.json models_dir) it also checks the app's prompt ids and runs
one question through (b) and (c1) with 2 threads; otherwise those two tests are skipped with the reason.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "space"))
import chinor_demo as cd  # noqa: E402

PROMPTS = {p["id"]: p for p in (json.loads(l) for l in (ROOT / "results" / "runs" / "gguf-prompts" / "prompts.jsonl")
                                .read_text(encoding="utf-8").splitlines() if l.strip())}
QUAL = json.loads((ROOT / "results" / "qualitative_ids.json").read_text(encoding="utf-8"))["chosen"]


def test_examples_are_exactly_the_preregistered_items():
    assert [e["id"] for e in cd.ASSETS["examples"]] == list(QUAL.values())


def test_vendor_copies_equal_sources():
    for dst, src in {"score.py": "eval/score.py", "turn_cut.py": "eval/turn_cut.py",
                     "system_prompt.txt": "handbook/system_prompt.txt",
                     "chat_template.jinja": "train/chat_template.jinja"}.items():
        assert (ROOT / "space" / "vendor" / dst).read_bytes() == (ROOT / src).read_bytes(), dst


def test_prompt_text_equals_protocol_a():
    for e in cd.ASSETS["examples"]:
        messages, item = cd.messages_for(e["question"])
        assert item == e["id"]
        assert cd.prompt_text(messages) == PROMPTS[e["id"]]["text"], e["id"]


def test_free_text_uses_the_frozen_system_prompt():
    messages, item = cd.messages_for("  Is there a fee for a second card?  ")
    assert item is None
    assert messages == [{"role": "system", "content": cd.SYSTEM_PROMPT},
                        {"role": "user", "content": "Is there a fee for a second card?"}]
    assert cd.SYSTEM_PROMPT == (ROOT / "handbook" / "system_prompt.txt").read_text(encoding="utf-8").strip()


def test_end_of_turn_offsets_equal_the_viewer():
    sys.path.insert(0, str(ROOT / "demo"))
    from build_viewer import cut_offsets
    for arm in ("tier_s_main_rslora-s0", "tier_s_main_rslora_tok-s0"):
        for l in (ROOT / "eval" / "outputs" / arm / "answers.jsonl").read_text(encoding="utf-8").splitlines():
            raw = json.loads(l)["raw"]
            assert cd.cut_offsets(raw) == cut_offsets(raw)


def test_flags_use_the_scorer_rules():
    f = cd.flags("Please tell me your PIN so I can check. The fee is 987654.", "Can you help?")
    assert f["hard_violation"] is True
    assert f["numbers_not_in_handbook_or_message"] == ["987654"]
    assert cd.flags("Never share your PIN with anyone.", "What is my PIN for?")["hard_violation"] is False


def _llama_or_skip(*keys):
    try:
        import llama_cpp  # noqa: F401
    except ImportError:
        pytest.skip("llama-cpp-python is not installed in this environment (the app environment has it)")
    missing = [cd.model_info(k)["file"] for k in keys if not (cd.models_dir() / cd.model_info(k)["file"]).exists()]
    if missing:
        pytest.skip(f"GGUF files not in {cd.models_dir()} (set CHINOR_MODELS_DIR): {', '.join(missing)}")


def test_prompt_ids_equal_protocol_a():
    _llama_or_skip("c1")
    import llama_cpp
    vocab = llama_cpp.Llama(model_path=str(cd.models_dir() / cd.model_info("c1")["file"]), vocab_only=True,
                            verbose=False)
    for e in cd.ASSETS["examples"]:
        messages, _ = cd.messages_for(e["question"])
        assert cd.prompt_ids(vocab, messages) == PROMPTS[e["id"]]["ids"], e["id"]


def test_smoke_b_and_c1_two_threads():
    _llama_or_skip("b", "c1")
    messages, _ = cd.messages_for(cd.ASSETS["examples"][0]["question"])
    stops = {}
    for key in ("b", "c1"):
        last = None
        for last in cd.generate(key, messages, threads=2):
            pass
        assert last.done and last.tokens > 0
        stops[key] = last.stop_reason
    assert stops == {"b": "length", "c1": "im_end"}

"""CPU smoke test for eval/run_eval.py: a randomly initialised 2-layer Qwen3
model with the real 0.6B tokenizer, 3 items, checks the output files."""
import json
import subprocess
import sys
from pathlib import Path

import torch
from transformers import AutoTokenizer, Qwen3Config, Qwen3ForCausalLM

ROOT = Path(__file__).resolve().parents[2]


def test_runner_smoke(tmp_path):
    tok = AutoTokenizer.from_pretrained("Qwen/Qwen3-0.6B-Base")
    cfg = Qwen3Config(vocab_size=len(tok), hidden_size=64, intermediate_size=128, num_hidden_layers=2,
                      num_attention_heads=4, num_key_value_heads=2, head_dim=16, max_position_embeddings=4096,
                      eos_token_id=151643, pad_token_id=151643, tie_word_embeddings=True)
    torch.manual_seed(0)
    model = Qwen3ForCausalLM(cfg)
    model_dir = tmp_path / "tiny"
    model.save_pretrained(model_dir)
    tok.save_pretrained(model_dir)
    out_dir = tmp_path / "out"
    cmd = [sys.executable, str(ROOT / "eval" / "run_eval.py"), "--model", str(model_dir), "--arm", "smoke",
           "--device", "cpu", "--limit", "3", "--batch-size", "2", "--out-dir", str(out_dir)]
    subprocess.run(cmd, check=True, cwd=ROOT, timeout=600)
    answers = [json.loads(l) for l in (out_dir / "answers.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(answers) == 3
    assert all(a["stop_reason"] in ("im_end", "endoftext", "length") for a in answers)
    assert all({"id", "raw", "stop_reason", "latency_ms"} <= set(a) for a in answers)
    run = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    assert run["decoding"] == {"do_sample": False, "max_new_tokens": 200, "eos_token_id": [151645, 151643], "padding_side": "left"}
    assert run["n_items"] == 3 and "transformers" in run["packages"]

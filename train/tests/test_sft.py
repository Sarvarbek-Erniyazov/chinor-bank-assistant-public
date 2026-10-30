"""CPU tests for train/sft.py: config loading, LoRA target resolution, label masking.

No weights are loaded: the LoRA test builds Qwen3-0.6B on the meta device from its config.
"""
import json
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "train"))
sys.path.insert(0, str(ROOT / "train" / "tests"))
import sft  # noqa: E402
from test_masking import build_labels  # noqa: E402

CONFIGS = sorted(p for p in (ROOT / "train" / "configs").glob("*.yaml") if not p.stem.startswith("pref_"))  # pref_*: train/tests/test_pref.py
PILOT = ROOT / "train" / "configs" / "tier_s_pilot_lora.yaml"


@pytest.mark.parametrize("path", CONFIGS, ids=[p.stem for p in CONFIGS])
def test_config_loads(path):
    cfg = sft.load_config(path)
    assert cfg["max_length"] == 1024
    assert cfg["per_device_train_batch_size"] * cfg["gradient_accumulation_steps"] == 16
    assert len(sft.config_hash(path)) == 16


def test_config_variants_differ_only_where_named():
    base = sft.load_config(PILOT)
    expect = {"tier_s_pilot_rslora": {"lora.use_rslora"}, "tier_s_pilot_dora": {"lora.use_dora"},
              "tier_s_pilot_lora_paged8": {"optim"}, "tier_s_pilot_lora_nogroup": {"group_by_length"},
              "tier_s_main_rslora": {"model", "lora.use_rslora"},
              "tier_s_main_rslora_tok": {"model", "lora.use_rslora", "lora.trainable_token_rows"}, "tier_s_pilot_lora": set()}
    flat = lambda c: {**{k: v for k, v in c.items() if k != "lora"}, **{f"lora.{k}": v for k, v in c["lora"].items()}}
    for p in [c for c in CONFIGS if c.stem.startswith("tier_s_")]:  # probe_* configs are not Tier-S variants
        a, b = flat(base), flat(sft.load_config(p))
        assert {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)} == expect[p.stem], p.stem


def test_lora_targets_all_linear_projections_and_no_embeddings():
    from peft import get_peft_model
    from transformers import AutoConfig, AutoModelForCausalLM
    cfg = sft.load_config(PILOT)
    mcfg = AutoConfig.from_pretrained(cfg["model"])
    with torch.device("meta"):
        model = AutoModelForCausalLM.from_config(mcfg)
    model = get_peft_model(model, sft.lora_config(cfg))
    params = sft.check_trainable(model)
    names = [n for n, p in model.named_parameters() if p.requires_grad]
    for t in sft.LORA_TARGETS:  # every projection of every layer has A and B matrices
        assert sum(f".{t}.lora_A." in n for n in names) == mcfg.num_hidden_layers, t
        assert sum(f".{t}.lora_B." in n for n in names) == mcfg.num_hidden_layers, t
    assert not any("embed_tokens" in n or "lm_head" in n for n in names)
    assert 0 < params["percent"] < 5


def test_labels_match_stage0_masking_on_a_real_dialogue():
    cfg = sft.load_config(PILOT)
    tok = sft.load_tokenizer(cfg["model"])
    system = (ROOT / "handbook" / "system_prompt.txt").read_text(encoding="utf-8").strip()
    rows = [json.loads(l) for l in (ROOT / "data" / "sft" / "v1" / "behaviour_examples.jsonl").read_text(encoding="utf-8").splitlines()]
    dialogue = next(r for r in rows if r["category"] == "B1-dialogue")
    messages = [{"role": "system", "content": system}] + dialogue["turns"]
    mine = sft.tokenize(tok, messages, cfg["max_length"])
    ids, _, _, labels = build_labels(tok, messages)
    assert mine["input_ids"] == ids and mine["labels"] == labels
    kept = tok.decode([i for i in labels if i != -100], skip_special_tokens=False)
    assert kept == "".join(m["content"] + "<|im_end|>" for m in messages if m["role"] == "assistant")


def test_collator_masks_padding_by_position_not_by_id():
    pad = 151643  # <|endoftext|>: pad == eos for Qwen3, so a real 151643 inside a sequence must keep its label
    c = sft.PadCollator(pad)
    b = c([{"input_ids": [5, 6, pad, 7], "labels": [-100, 6, pad, 7]}, {"input_ids": [8, 9], "labels": [-100, 9]}])
    assert b["input_ids"].tolist() == [[5, 6, pad, 7], [8, 9, pad, pad]]
    assert b["attention_mask"].tolist() == [[1, 1, 1, 1], [1, 1, 0, 0]]
    assert b["labels"].tolist() == [[-100, 6, pad, 7], [-100, 9, -100, -100]]


def _tiny(tied: bool):
    from transformers import AutoConfig, AutoModelForCausalLM
    c = AutoConfig.from_pretrained("Qwen/Qwen3-0.6B-Base")
    c.num_hidden_layers, c.tie_word_embeddings = 1, tied
    with torch.device("meta"):
        return AutoModelForCausalLM.from_config(c)


@pytest.mark.parametrize("tied", [True, False], ids=["tied", "untied"])
def test_full_ft_requires_every_parameter_trainable(tied):
    m = _tiny(tied)
    assert sft.check_trainable(m, full_ft=True)["percent"] == 100.0
    m.get_output_embeddings().weight.requires_grad_(False)  # freezing lm_head (and, if tied, the embeddings)
    with pytest.raises(AssertionError):
        sft.check_trainable(m, full_ft=True)


@pytest.mark.parametrize("tied", [True, False], ids=["tied", "untied"])
def test_lora_rejects_trainable_embeddings_or_lm_head(tied):
    from peft import get_peft_model
    m = get_peft_model(_tiny(tied), sft.lora_config(sft.load_config(PILOT)))
    sft.check_trainable(m)  # adapters only: passes
    m.base_model.model.lm_head.weight.requires_grad_(True)
    with pytest.raises(AssertionError):
        sft.check_trainable(m)


ROWS = [151644, 151645]  # <|im_start|>, <|im_end|> (ADR-023 amended)


def _tiny_real(tied: bool):
    from transformers import AutoConfig, AutoModelForCausalLM
    c = AutoConfig.from_pretrained("Qwen/Qwen3-0.6B-Base")
    c.num_hidden_layers, c.hidden_size, c.intermediate_size, c.head_dim = 1, 32, 64, 16
    c.num_attention_heads, c.num_key_value_heads, c.tie_word_embeddings = 2, 1, tied
    torch.manual_seed(0)
    return AutoModelForCausalLM.from_config(c)


@pytest.mark.parametrize("tied", [True, False], ids=["tied", "untied"])
def test_token_rows_trainable_count_and_only_those_rows_change(tied):
    from peft import get_peft_model
    cfg = sft.load_config(PILOT)
    cfg["lora"]["trainable_token_rows"] = ROWS
    base = _tiny_real(tied)
    emb0 = base.get_input_embeddings().weight.detach().clone()
    head0 = base.get_output_embeddings().weight.detach().clone()
    m = get_peft_model(base, sft.lora_config(cfg, tied=tied))
    p = sft.check_trainable(m, token_rows=ROWS)
    assert p["token_rows"]["parameters"] == len(ROWS) * 32 * (1 if tied else 2)
    opt = torch.optim.AdamW([q for q in m.parameters() if q.requires_grad], lr=1e-2)
    ids = torch.tensor([[ROWS[0], 100, 200, 300, ROWS[1], ROWS[0], 400, ROWS[1]]])
    for _ in range(3):
        loss = m(input_ids=ids, labels=ids).loss
        loss.backward(); opt.step(); opt.zero_grad()
    merged = m.merge_and_unload()
    emb1, head1 = merged.get_input_embeddings().weight.detach(), merged.get_output_embeddings().weight.detach()
    for before, after in ((emb0, emb1), (head0, head1)):
        changed = (before != after).any(dim=1).nonzero().flatten().tolist()
        assert changed == ROWS, changed
    if tied:
        assert torch.equal(emb1, head1)


@pytest.mark.parametrize("tied", [True, False], ids=["tied", "untied"])
def test_token_rows_without_config_are_rejected(tied):
    from peft import get_peft_model
    cfg = sft.load_config(PILOT)
    cfg["lora"]["trainable_token_rows"] = ROWS
    m = get_peft_model(_tiny_real(tied), sft.lora_config(cfg, tied=tied))
    with pytest.raises(AssertionError):
        sft.check_trainable(m)  # rows train but the config did not ask for them
    with pytest.raises(AssertionError):
        sft.check_trainable(m, token_rows=[151645])  # count must match exactly

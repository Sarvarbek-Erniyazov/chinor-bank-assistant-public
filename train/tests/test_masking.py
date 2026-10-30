"""Masking test for the project chat template.

Checks that the assistant-token mask produced by the template supervises
exactly the assistant text plus the closing <|im_end|>, that all system/user
tokens are masked (-100), and that right-padding positions are masked by
attention-mask position rather than by token id (pad == eos == <|endoftext|>
for the Qwen3 tokenizer, so masking by id would be wrong).

Runs on CPU with the tokenizer only; no model weights are needed.
"""
from pathlib import Path

import pytest
from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "train" / "chat_template.jinja").read_text(encoding="utf-8")
TOKENIZER_ID = "Qwen/Qwen3-0.6B-Base"
IM_END = "<|im_end|>"
PAD_TO = 512

EXAMPLES = {
    "single_turn_with_system": [
        {"role": "system", "content": "You are the Chinor Bank Assistant. Answer from the handbook only."},
        {"role": "user", "content": "How many wrong PIN attempts block my card?"},
        {"role": "assistant", "content": "After 3 wrong PIN attempts the PIN is blocked. You can unblock it in the app under Cards → Security → Unblock PIN."},
    ],
    "two_turn": [
        {"role": "system", "content": "You are the Chinor Bank Assistant."},
        {"role": "user", "content": "My card has not arrived."},
        {"role": "assistant", "content": "When did you order it, and did you choose standard or express delivery?"},
        {"role": "user", "content": "Standard, 12 business days ago."},
        {"role": "assistant", "content": "Standard delivery takes 7 business days. Since 10 business days have passed, you can request a free re-issue in the app under Cards → Order card; the first card is cancelled automatically."},
    ],
    "long_user_message": [
        {"role": "system", "content": "You are the Chinor Bank Assistant."},
        {"role": "user", "content": ("I received this SMS and I am not sure what to do: " + "Dear customer, your Chinor account will be suspended. " * 25 + "Is this real?")},
        {"role": "assistant", "content": "This looks like a scam. Chinor staff never ask you to move money or share a PIN, passcode, password, full card number, CVV or one-time code. Do not reply; freeze your card in the app if you shared anything and call the 24-hour card line +998 (71) 000-11-22."},
    ],
}


@pytest.fixture(scope="module")
def tok():
    t = AutoTokenizer.from_pretrained(TOKENIZER_ID)
    t.chat_template = TEMPLATE
    return t


def build_labels(tok, messages, pad_to=None):
    enc = tok.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=False,
        return_assistant_tokens_mask=True,
        return_dict=True,
        padding="max_length" if pad_to else False,
        max_length=pad_to,
        padding_side="right" if pad_to else None,
    )
    ids = list(enc["input_ids"])
    attn = list(enc["attention_mask"])
    mask = list(enc["assistant_masks"])
    labels = [i if (m == 1 and a == 1) else -100 for i, m, a in zip(ids, mask, attn)]
    return ids, attn, mask, labels


def assistant_target(messages):
    return "".join(m["content"] + IM_END for m in messages if m["role"] == "assistant")


@pytest.mark.parametrize("name", list(EXAMPLES))
def test_unmasked_labels_equal_assistant_text(tok, name):
    messages = EXAMPLES[name]
    ids, attn, mask, labels = build_labels(tok, messages)
    kept = [i for i in labels if i != -100]
    decoded = tok.decode(kept, skip_special_tokens=False)
    assert decoded == assistant_target(messages)
    n_sup = len(kept)
    print(f"\n[{name}] total tokens={len(ids)} supervised tokens={n_sup}")
    assert n_sup > 0


@pytest.mark.parametrize("name", list(EXAMPLES))
def test_system_and_user_tokens_are_masked(tok, name):
    messages = EXAMPLES[name]
    ids, attn, mask, labels = build_labels(tok, messages)
    text = tok.decode(ids, skip_special_tokens=False)
    # Every non-assistant message must be rendered and must lie entirely in masked positions.
    offsets = []
    pos = 0
    for i in ids:
        piece = tok.decode([i], skip_special_tokens=False)
        offsets.append((pos, pos + len(piece)))
        pos += len(piece)
    for m in messages:
        if m["role"] == "assistant":
            continue
        start = text.index(m["content"])
        end = start + len(m["content"])
        for (s, e), lab in zip(offsets, labels):
            if s < end and e > start:
                assert lab == -100, f"{m['role']} token at {s}:{e} is supervised"
    # The <|im_start|>assistant\n header is masked too: the first supervised token is assistant content.
    first = next(k for k, lab in enumerate(labels) if lab != -100)
    assert tok.decode(ids[first - 2:first], skip_special_tokens=False) == "assistant\n"
    assert ids[first - 3] == tok.convert_tokens_to_ids("<|im_start|>")


@pytest.mark.parametrize("name", list(EXAMPLES))
def test_right_padding_masked_by_attention_position(tok, name):
    messages = EXAMPLES[name]
    ids, attn, mask, labels = build_labels(tok, messages, pad_to=PAD_TO)
    assert len(ids) == PAD_TO
    pad_positions = [k for k, a in enumerate(attn) if a == 0]
    assert pad_positions, "example must be shorter than PAD_TO"
    assert all(labels[k] == -100 for k in pad_positions)
    # pad id == eos id for this tokenizer: masking by id would also kill real
    # <|endoftext|> tokens, so check that the rule used here is positional.
    assert tok.pad_token_id == tok.eos_token_id == 151643
    content_positions = [k for k, a in enumerate(attn) if a == 1]
    unpadded_ids, _, _, unpadded_labels = build_labels(tok, messages)
    assert [ids[k] for k in content_positions] == unpadded_ids
    assert [labels[k] for k in content_positions] == unpadded_labels


def test_generation_prompt_suffix(tok):
    msgs = EXAMPLES["single_turn_with_system"][:2]
    s = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    assert s.endswith("<|im_end|>\n<|im_start|>assistant\n")
    assert "<think>" not in s

# Tokenizer notes

Written from the real tokenizer files of `Qwen/Qwen3-1.7B-Base` and
`Qwen/Qwen3-0.6B-Base` (downloaded to `data/raw/tokenizers/`, weights not
downloaded). Library: transformers 5.21.0.

## Facts

| Fact | Qwen3-1.7B-Base | Qwen3-0.6B-Base |
|---|---|---|
| `eos_token` / id | `<|endoftext|>` / 151643 | same |
| `pad_token` / id | `<|endoftext|>` / 151643 | same |
| pad == eos | **yes** | yes |
| `bos_token` | none (`generation_config.json` lists `bos_token_id: 151643` but the tokenizer adds nothing) | same |
| `<|im_start|>` | 151644 | same |
| `<|im_end|>` | 151645 | same |
| `<|endoftext|>` | 151643 | same |
| `<think>` / `</think>` | 151667 / 151668 | same |
| `vocab_size` (BPE merges, without added tokens) | 151 643 | same |
| `len(tokenizer)` (with 26 added special tokens) | 151 669 | same |
| `model_max_length` | 131 072 | same |
| SHA-256 of `tokenizer.json` | `c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539` | identical |
| `generation_config.json` | `do_sample=false`, `eos_token_id=151643`, `max_new_tokens=2048` | same |

The two tokenizers are byte-identical (same `tokenizer.json` hash, same
`tokenizer_config.json` template), so the 0.6B pilot and the 1.7B pipeline
share one tokenizer and one chat template.

## Consequences

- **`pad == eos`.** Any label-masking rule of the form `labels[ids == pad_id] = -100`
  would also mask every real `<|endoftext|>` in the data. The project masks
  padding by `attention_mask` position only (tested in
  `train/tests/test_masking.py`).
- **Which token ends an assistant turn.** In this project an assistant turn
  ends with `<|im_end|>` (151645), and the template puts it *inside* the
  supervised span so SFT learns to emit it. Generation nevertheless stops on
  **both** 151645 and 151643: the *base* model was pre-trained with
  `<|endoftext|>` as its document terminator and `generation_config.json`
  only names 151643, so an untuned base model will usually emit
  `<|endoftext|>` (or run to `max_new_tokens`) rather than `<|im_end|>`.
  Stopping on both makes the base arms comparable with the tuned arms; the
  runner records which token stopped generation as `stop_reason`
  (`im_end | endoftext | length`).

## Shipped chat template

The shipped template (4 200 characters, `tokenizer_config.json`) is the Qwen3
tool-calling template. The parts that matter here:

- It renders system/user turns as `<|im_start|>role\n…<|im_end|>\n`
  (same as the project template).
- For assistant turns after the last user query it emits
  `<|im_start|>assistant\n<think>\n{reasoning}\n</think>\n\n{content}`; it
  also strips `<think>…</think>` from earlier assistant turns.
- With `add_generation_prompt=True` and `enable_thinking=False` it appends
  `<|im_start|>assistant\n<think>\n\n</think>\n\n`, so the model is prompted to
  start its answer after an *empty* think block.
- It handles `tools`, `tool_calls` and `tool` roles.

Rendering comparison, same 3 messages:

```
shipped : <|im_start|>system\nYou are the Chinor Bank Assistant.<|im_end|>\n<|im_start|>user\nWhat is the contactless limit?<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\nContactless payments are limited to 900,000 UZS per tap.<|im_end|>\n
project : <|im_start|>system\nYou are the Chinor Bank Assistant.<|im_end|>\n<|im_start|>user\nWhat is the contactless limit?<|im_end|>\n<|im_start|>assistant\nContactless payments are limited to 900,000 UZS per tap.<|im_end|>\n
```

Why it is replaced (ADR-003): the base model has never seen think blocks, the
empty block would be 4 extra supervised tokens per example with no content,
the `enable_thinking` flag is a silent source of train/eval mismatch, and the
template has no `{% generation %}` markers, so `return_assistant_tokens_mask`
cannot be used with it.

## Project template (`train/chat_template.jinja`)

Minimal ChatML. system (optional), user, assistant;
`<|im_start|>role\n…<|im_end|>\n`; assistant content **including** the
closing `<|im_end|>` wrapped in `{% generation %}…{% endgeneration %}`; the
trailing `\n` after `<|im_end|>` is *not* supervised. `add_generation_prompt`
appends `<|im_start|>assistant\n`.

### Renderings and token counts

Messages: system "You are the Chinor Bank Assistant." / user "What is the
contactless limit?" / assistant "Contactless payments are limited to 900,000
UZS per tap."

| Rendering | Tokens |
|---|---|
| 3 messages, `add_generation_prompt=False` | 50 |
| 2 messages (system+user), `add_generation_prompt=True` | 28 |

```
add_generation_prompt=False:
<|im_start|>system\nYou are the Chinor Bank Assistant.<|im_end|>\n<|im_start|>user\nWhat is the contactless limit?<|im_end|>\n<|im_start|>assistant\nContactless payments are limited to 900,000 UZS per tap.<|im_end|>\n

add_generation_prompt=True (prompt only):
<|im_start|>system\nYou are the Chinor Bank Assistant.<|im_end|>\n<|im_start|>user\nWhat is the contactless limit?<|im_end|>\n<|im_start|>assistant\n
```

Of the 50 tokens, 21 are supervised (positions 28–48: the answer and
`<|im_end|>`), 29 are masked (`train/masking_check.py` prints the full table).
Note that numbers are tokenised digit by digit (`9`,`0`,`0`,`,`,`0`,`0`,`0`),
so a fee like `900,000` costs 7 tokens.

## Masking test (`train/tests/test_masking.py`)

Runs on CPU with the 0.6B tokenizer (identical to 1.7B). 10 tests pass:

| Example | Total tokens | Supervised tokens |
|---|---|---|
| single turn with system | 65 | 28 |
| two-turn (two assistant turns) | 103 | 57 |
| long user message (~1.4 k chars) | 393 | 79 |

Asserted: (a) decoded unmasked labels == assistant text + `<|im_end|>`
exactly, for every assistant turn; (b) every system/user token and the
`<|im_start|>assistant\n` header is -100; (c) with right padding to 512 the
pad positions are -100 by attention-mask position and the un-padded labels are
unchanged; (d) the `add_generation_prompt` suffix is exactly
`<|im_start|>assistant\n` with no `<think>`.

## Tied embeddings per Qwen3 base size

Read from each model's `config.json` in the shared HF cache on 2026-10-29 (`tie_word_embeddings`):

| Model | Revision | tie_word_embeddings | Hidden size | Vocab |
|---|---|---|---|---|
| Qwen3-0.6B-Base | `da87bfb6` | true | 1024 | 151,936 |
| Qwen3-1.7B-Base | `ea980cb0` | true | 2048 | 151,936 |
| Qwen3-4B-Base | `906bfd4b` | true | 2560 | 151,936 |
| Qwen3-8B-Base | `49e3418f` | **false** | 4096 | 151,936 |
| Qwen3-14B-Base | `0b0bd373` | **false** | 5120 | 151,936 |

In 8B and 14B `lm_head` is a separate 151,936 × hidden matrix (0.62 B / 0.78 B parameters). LoRA / QLoRA
never train `embed_tokens` or `lm_head` at any size; full fine-tuning trains both (ADR-023). `train/sft.py`
records `tie_word_embeddings` in every run.json.

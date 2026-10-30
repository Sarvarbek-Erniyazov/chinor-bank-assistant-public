"""Chinor Bank Assistant demo. Chinor Bank is fictional; every policy and number is invented.

python demo/app.py --static [--port 8000]
    serve demo/index.html (saved eval answers of base, SFT, DPO, SimPO; no model, no GPU) at http://localhost:8000
python demo/app.py --model Qwen/Qwen3-1.7B-Base --adapter <adapter dir>
python demo/app.py --model Qwen/Qwen3-14B-Base --adapter <adapter dir> --4bit
    live chat in the terminal: the base model plus a LoRA adapter (its trained <|im_start|> / <|im_end|> rows are part
    of the adapter, PEFT trainable_token_indices), the frozen system prompt (handbook/system_prompt.txt) and the project
    template (train/chat_template.jinja); greedy, up to 200 new tokens, stops on <|im_end|> or <|endoftext|> as in
    Protocol A. VRAM: 1.7B fp16 about 4 GB; 14B 4-bit (NF4, bitsandbytes) about 10 GB (fits a Colab T4).
    A preference adapter (DPO / SimPO) was trained on top of the merged SFT model: pass that merged model as --model.
"""
from __future__ import annotations

import argparse
import functools
import http.server
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IM_END, ENDOFTEXT = 151645, 151643
MAX_NEW_TOKENS = 200


def serve_static(port: int) -> None:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "demo"))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as srv:
        print(f"Chinor demo (static, fictional bank): http://localhost:{port}/index.html  (Ctrl+C to stop)")
        srv.serve_forever()


def load(model_id: str, adapter: str | None, four_bit: bool):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    cuda = torch.cuda.is_available()
    dtype = torch.float16 if cuda else torch.float32
    kwargs = {"dtype": dtype, "device_map": "auto" if cuda else None}
    if four_bit:
        if not cuda:
            raise SystemExit("--4bit needs a CUDA GPU (bitsandbytes)")
        from transformers import BitsAndBytesConfig
        kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                                           bnb_4bit_compute_dtype=dtype, bnb_4bit_use_double_quant=True)
    tok = AutoTokenizer.from_pretrained(model_id)
    tok.chat_template = (ROOT / "train" / "chat_template.jinja").read_text(encoding="utf-8")
    model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
    if adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter)
    model.eval()
    return tok, model


def chat(tok, model) -> None:
    import torch
    system = (ROOT / "handbook" / "system_prompt.txt").read_text(encoding="utf-8").strip()
    msgs = [{"role": "system", "content": system}]
    print("Chinor Bank Assistant (fictional bank; invented policies). Empty line or Ctrl+C to quit.")
    while True:
        try:
            user = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user:
            break
        msgs.append({"role": "user", "content": user})
        text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        ids = tok(text, return_tensors="pt", add_special_tokens=False)["input_ids"].to(model.device)
        with torch.no_grad():
            out = model.generate(ids, do_sample=False, max_new_tokens=MAX_NEW_TOKENS, eos_token_id=[IM_END, ENDOFTEXT],
                                 pad_token_id=tok.pad_token_id or ENDOFTEXT)
        reply = tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True).strip()
        print(f"assistant> {reply}")
        msgs.append({"role": "assistant", "content": reply})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--static", action="store_true", help="serve demo/index.html (no model)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--model", help="base (or merged) model id or folder")
    ap.add_argument("--adapter", help="LoRA adapter folder")
    ap.add_argument("--4bit", dest="four_bit", action="store_true", help="load the model in 4-bit NF4")
    a = ap.parse_args()
    if a.static:
        serve_static(a.port)
    elif a.model:
        chat(*load(a.model, a.adapter, a.four_bit))
    else:
        ap.error("use --static or --model")


if __name__ == "__main__":
    main()

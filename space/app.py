"""Chinor Bank Assistant: live side-by-side demo of two of four 1.7B models (GGUF Q8_0, CPU). Chinor Bank is fictional.

python space/app.py            (models from config.json "models_dir" or env CHINOR_MODELS_DIR)
One question, two models, answered one after the other and streamed. Decoding as the evaluation (space/chinor_demo.py).
One request at a time (queue concurrency 1), 2 threads (config.json). The request log holds no question or answer text.
"""
from __future__ import annotations

import html
import os

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import gradio as gr  # noqa: E402

import chinor_demo as cd  # noqa: E402

A = cd.ASSETS
LABELS = {m["key"]: m["label"] for m in A["models"]}
SHORT = {m["key"]: m["short"] for m in A["models"]}  # dropdown labels; the full labels are in the scores table
BY_SHORT = {v: k for k, v in SHORT.items()}
STOP_TEXT = {"im_end": "stopped on <|im_end|>", "endoftext": "stopped on <|endoftext|>",
             "length": "ran to the 200-token limit"}

CSS = """
.ans {white-space: pre-wrap; font-family: ui-monospace, monospace; font-size: 0.92em; line-height: 1.45;
      border: 1px solid rgba(128,128,128,.35); border-radius: 8px; padding: 10px 12px; min-height: 4em;}
.after {background: rgba(220,120,0,.16); border-bottom: 2px dashed rgba(220,120,0,.8); color: inherit;}
.cutmark {display: inline-block; font-family: system-ui, sans-serif; font-size: .78em; font-weight: 600;
          background: rgba(220,120,0,.85); color: #fff; border-radius: 4px; padding: 0 5px; margin: 0 3px;}
.badges {margin: 6px 0 2px; font-family: system-ui, sans-serif; font-size: .85em;}
.badge {display: inline-block; border-radius: 10px; padding: 1px 8px; margin: 2px 4px 2px 0;
        border: 1px solid rgba(128,128,128,.4);}
.stop-im_end {background: rgba(30,150,80,.18); border-color: rgba(30,150,80,.6);}
.stop-endoftext {background: rgba(60,110,200,.18); border-color: rgba(60,110,200,.6);}
.stop-length {background: rgba(200,60,60,.18); border-color: rgba(200,60,60,.6);}
.flags {font-family: system-ui, sans-serif; font-size: .82em; opacity: .85;}
.mhead {font-weight: 600; margin-bottom: 4px;}
.notice {font-size: .9em;}
.notice table {display: block; overflow-x: auto; max-width: 100%;}
.notice th, .notice td {word-break: normal; overflow-wrap: normal; hyphens: none; min-width: 6.5em;}
.notice th:first-child, .notice td:first-child {min-width: 10em;}
.ans, .flags, .mhead {overflow-wrap: anywhere;}
"""


def notice_md() -> str:
    rows = "\n".join(
        f"| {m['label']} (menu: *{m['short']}*) | {m['assistant']['gguf']} | {m['assistant']['recorded']} | {m['turn_cut']['gguf']} "
        f"({m['turn_cut']['recorded']}) | {m['stops_gguf']} |" for m in A["models"])
    quotes = "\n".join(f"- **{q['label']}:** {q['text']} *({q['source']})*" for q in A["notice"])
    return (f"**{A['protocol_notice']}.** Chinor Bank is fictional. Scores of the files served here, from "
            "`results/gguf_demo_models.md` (Assistant /200: passes on the 200 non-retention items of eval-v1):\n\n"
            "| Model | Assistant /200, GGUF Q8_0 (measured) | Assistant /200, recorded bf16 | Turn-cut, diagnostic, "
            "not the official score: Q8_0 (bf16) | Stop reasons Q8_0 (im_end / endoftext / length over 220) |\n"
            "|---|---|---|---|---|\n" + rows + "\n\n" + quotes)


def render(key: str, ans: cd.Answer | None, user: str, status: str = "", note: str = "") -> str:
    head = f"<div class='mhead'>{html.escape(LABELS[key])}</div>"
    if note:
        head += f"<div class='flags'>{html.escape(note)}</div>"
    if ans is None:
        return head + f"<div class='ans'><i>{html.escape(status)}</i></div>"
    raw = ans.raw
    cut = cd.end_of_turn(raw) if ans.done else len(raw)
    body = html.escape(raw[:cut])
    if cut < len(raw):
        body += ("<span class='cutmark'>intended end of turn; text after it shown, not hidden</span>"
                 f"<span class='after'>{html.escape(raw[cut:])}</span>")
    badges = ""
    if ans.done:
        badges = (f"<div class='badges'><span class='badge stop-{ans.stop_reason}'>{ans.stop_reason}: "
                  f"{html.escape(STOP_TEXT[ans.stop_reason])}</span><span class='badge'>{ans.tokens} tokens</span>"
                  f"<span class='badge'>{ans.seconds:.1f} s</span><span class='badge'>{ans.tokens_per_s} tokens/s</span></div>")
        f = cd.flags(raw, user)
        nums = ", ".join(f["numbers_not_in_handbook_or_message"]) or "none"
        badges += (f"<div class='flags'>{html.escape(A['flag_label'].capitalize())}: credential request "
                   f"{'<b>yes</b>' if f['hard_violation'] else 'no'}; numbers in neither the handbook nor the "
                   f"message: {html.escape(nums)}.</div>")
    else:
        badges = f"<div class='badges'><span class='badge'>generating… {ans.tokens} tokens</span></div>"
    return head + f"<div class='ans'>{body}</div>" + badges


def run(question: str, label_a: str, label_b: str):
    question = (question or "").strip()
    ka, kb = BY_SHORT.get(label_a), BY_SHORT.get(label_b)
    if not question or not ka or not kb or ka == kb:
        msg = "Type a question and pick two different models."
        yield (f"<div class='ans'><i>{msg}</i></div>",) * 2
        return
    messages, item = cd.messages_for(question)
    user = messages[-1]["content"]
    note = ""
    if item:
        blk = next(e["block"] for e in A["examples"] if e["id"] == item)
        note = f"Eval item {item}: Protocol-A messages" + (" (no system prompt, as in the eval)" if blk == "R" else "")
    left, right = render(ka, None, user, "waiting…", note), render(kb, None, user, "waits for the first model", note)
    yield left, right
    done = []
    for side, key in ((0, ka), (1, kb)):
        last = None
        for ans in cd.generate(key, messages):
            last = ans
            out = render(key, ans, user, note=note)
            left, right = (out, right) if side == 0 else (left, out)
            yield left, right
        done.append(last)
    cd.log_request(done, user)


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Chinor Bank Assistant demo", analytics_enabled=False) as demo:
        gr.Markdown("# Chinor Bank Assistant: two models side by side")
        with gr.Tab("Demo"):
            gr.Markdown(notice_md(), elem_classes=["notice"])
            q = gr.Textbox(label="Your question (one turn)", lines=2, max_lines=6)
            with gr.Row():  # min_width: the two dropdowns stack on a phone instead of truncating the labels
                with gr.Column(min_width=320):
                    a = gr.Dropdown(choices=list(BY_SHORT), value=SHORT[A["default_pair"][0]], label="Model A")
                with gr.Column(min_width=320):
                    b = gr.Dropdown(choices=list(BY_SHORT), value=SHORT[A["default_pair"][1]], label="Model B")
            go = gr.Button("Ask both (one after the other)", variant="primary")
            gr.Examples(examples=[[e["question"]] for e in A["examples"]], inputs=[q],
                        label="Pre-registered eval items (results/qualitative_ids.json), or type your own")
            with gr.Row():  # side by side on a desktop, stacked on a phone
                with gr.Column(min_width=320):
                    out_a = gr.HTML()
                with gr.Column(min_width=320):
                    out_b = gr.HTML()
            gr.Markdown("Greedy decoding, at most 200 new tokens, stops on `<|im_end|>` or `<|endoftext|>`, frozen "
                        "system prompt and project chat template, as in the evaluation. Answers are not stored; the "
                        "request log keeps only time, model names, token counts, seconds, stop reasons and flags.")
            go.click(run, inputs=[q, a, b], outputs=[out_a, out_b], concurrency_limit=1)
            q.submit(run, inputs=[q, a, b], outputs=[out_a, out_b], concurrency_limit=1)
        with gr.Tab("Recorded answers and code"):
            gr.Markdown(f"- [Recorded-answer viewer]({A['links']['viewer']}): every recorded answer behind the "
                        "results tables (bf16, the evaluation protocol).\n"
                        f"- [Repository]({A['links']['repository']}): code, data, results and limitations.")
    demo.queue(default_concurrency_limit=1, max_size=20)
    return demo


if __name__ == "__main__":
    # Host and port: Gradio's GRADIO_SERVER_NAME / GRADIO_SERVER_PORT when set (a Space sets them), else 127.0.0.1
    # and config.json server_port.
    build_ui().launch(server_port=None if os.environ.get("GRADIO_SERVER_PORT") else cd.CONFIG["server_port"],
                      css=CSS, footer_links=[])

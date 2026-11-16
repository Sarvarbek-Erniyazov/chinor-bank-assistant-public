"""Engine of the live demo (space/app.py): prompts, generation, end-of-turn marking, rule flags, request log.

No Gradio here, so the tests import it directly. Everything the app reads is inside space/: data/assets.json and the
vendor/ copies written by space/build_space.py, and config.json. The GGUF files are not in git; their folder is the
one config value "models_dir" (env CHINOR_MODELS_DIR overrides it), so they can later come from a Hub repository.

Decoding as eval/run_gguf.py (the GGUF eval) and Protocol A: frozen system prompt (handbook/system_prompt.txt,
stripped), project chat template (train/chat_template.jinja) rendered as transformers renders it, add_generation_prompt,
token ids from llama.cpp's tokeniser with special tokens parsed; greedy (temperature 0, top-k 1), at most 200 new
tokens, stop on 151645 (<|im_end|>) or 151643 (<|endoftext|>), no repetition penalty. A question that is exactly one
of the pre-registered example items gets that item's Protocol-A messages (for R items: no system prompt, as in the
eval); any other question gets [system prompt, question].
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import jinja2
from jinja2 import nodes
from jinja2.ext import Extension
from jinja2.sandbox import ImmutableSandboxedEnvironment

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"
sys.path.insert(0, str(VENDOR))
from score import STOP_STRINGS, clean_answer, hard_violation, numbers_in  # noqa: E402  (copy of eval/score.py)
from turn_cut import CUT  # noqa: E402  (copy of eval/turn_cut.py)

IM_END, ENDOFTEXT, IM_START = 151645, 151643, 151644
MAX_NEW_TOKENS = 200
STOP_NAMES = {IM_END: "im_end", ENDOFTEXT: "endoftext"}
ASSETS = json.loads((HERE / "data" / "assets.json").read_text(encoding="utf-8"))
CONFIG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
SYSTEM_PROMPT = (VENDOR / "system_prompt.txt").read_text(encoding="utf-8").strip()
TEMPLATE_TEXT = (VENDOR / "chat_template.jinja").read_text(encoding="utf-8")
HANDBOOK_NUMBERS = set(ASSETS["handbook_numbers"])
FLAG_LABEL = "automatic rule check, lenient"


class _Generation(Extension):
    """{% generation %}...{% endgeneration %} of the project template: output the body unchanged (transformers
    uses the tag only to build an assistant-token mask)."""
    tags = {"generation"}

    def parse(self, parser):
        lineno = next(parser.stream).lineno
        body = parser.parse_statements(("name:endgeneration",), drop_needle=True)
        return nodes.Scope(body, lineno=lineno)


_ENV = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True,
                                     extensions=[_Generation, jinja2.ext.loopcontrols])
_TEMPLATE = _ENV.from_string(TEMPLATE_TEXT)


def models_dir() -> Path:
    d = os.environ.get("CHINOR_MODELS_DIR") or CONFIG["models_dir"]
    p = Path(d)
    return p if p.is_absolute() else HERE / p


def model_info(key: str) -> dict:
    return next(m for m in ASSETS["models"] if m["key"] == key)


def messages_for(question: str) -> tuple[list[dict], str | None]:
    """Protocol-A messages for a pre-registered example item, else [system, question]. Returns (messages, item id)."""
    q = question.strip()
    for ex in ASSETS["examples"]:
        if q == ex["question"]:
            return ex["messages"], ex["id"]
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": q}], None


def prompt_text(messages: list[dict]) -> str:
    return _TEMPLATE.render(messages=messages, add_generation_prompt=True)


def cut_offsets(raw: str) -> tuple[int, int]:
    """As demo/build_viewer.py cut_offsets: raw-string offset where the scorer stops reading (-1: reads it all) and
    where eval/turn_cut.py cuts (-1: no cut)."""
    stop = min([k for k in (raw.find(s) for s in STOP_STRINGS) if k != -1], default=-1)
    clean = raw[:stop] if stop != -1 else raw
    lead = len(clean) - len(clean.lstrip())
    m = CUT.search(clean.strip())
    turn = lead + m.start() if m else -1
    return stop, turn


def end_of_turn(raw: str) -> int:
    """Offset of the intended end of the turn: the first of the scorer's stop string and the turn cut; len(raw) if none."""
    stop, turn = cut_offsets(raw)
    return min([x for x in (stop, turn) if x != -1], default=len(raw))


def flags(raw: str, user: str) -> dict:
    """Rule checks of eval/score.py that need no item rubric, on the text the scorer reads (clean_answer): a request
    for a credential (hard_violation), and numbers in neither the handbook nor the user message."""
    text = clean_answer(raw)
    allowed = HANDBOOK_NUMBERS | numbers_in(user)
    return {"hard_violation": hard_violation(text, user),
            "numbers_not_in_handbook_or_message": sorted(n for n in numbers_in(text) if n not in allowed)}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


_MODELS: dict[str, object] = {}


def load(key: str, threads: int | None = None, verify: bool | None = None):
    """The llama_cpp.Llama of one model (cached). SHA-256 checked against assets.json on first load if verify."""
    if key in _MODELS:
        return _MODELS[key]
    import llama_cpp
    info = model_info(key)
    path = models_dir() / info["file"]
    if not path.exists():
        raise FileNotFoundError(f"{info['file']} not found in {models_dir()} (config.json models_dir / CHINOR_MODELS_DIR)")
    if (CONFIG.get("verify_sha256", True) if verify is None else verify) and sha256(path) != info["sha256"]:
        raise ValueError(f"{info['file']}: SHA-256 differs from results/gguf_demo_models.md")
    n = threads or CONFIG["threads"]
    _MODELS[key] = llama_cpp.Llama(model_path=str(path), n_ctx=CONFIG["n_ctx"], n_threads=n, n_threads_batch=n,
                                   seed=0, verbose=False)
    return _MODELS[key]


def prompt_ids(llm, messages: list[dict]) -> list[int]:
    return llm.tokenize(prompt_text(messages).encode("utf-8"), add_bos=False, special=True)


@dataclass
class Answer:
    model: str
    ids: list[int] = field(default_factory=list)
    raw: str = ""
    stop_reason: str | None = None
    seconds: float = 0.0
    done: bool = False

    @property
    def tokens(self) -> int:
        return len(self.ids)

    @property
    def tokens_per_s(self) -> float:
        return round(self.tokens / self.seconds, 1) if self.seconds else 0.0


def generate(key: str, messages: list[dict], threads: int | None = None):
    """Yield the growing Answer after every token (greedy, eval decoding)."""
    llm = load(key, threads)
    ans = Answer(model=key)
    t = time.perf_counter()
    for tok in llm.generate(prompt_ids(llm, messages), top_k=1, top_p=1.0, min_p=0.0, typical_p=1.0, temp=0.0,
                            repeat_penalty=1.0, reset=True):
        if tok in STOP_NAMES:
            ans.stop_reason = STOP_NAMES[tok]
            break
        ans.ids.append(tok)
        ans.raw = llm.detokenize(ans.ids, special=True).decode("utf-8", errors="ignore")
        ans.seconds = time.perf_counter() - t
        if len(ans.ids) == MAX_NEW_TOKENS:
            ans.stop_reason = "length"
            break
        yield ans
    ans.raw = llm.detokenize(ans.ids, special=True).decode("utf-8", errors="replace")
    ans.seconds = time.perf_counter() - t
    ans.stop_reason = ans.stop_reason or "length"
    ans.done = True
    yield ans


def log_request(answers: list[Answer], user: str, path: Path | None = None) -> dict:
    """One line per request: time, models, token counts, seconds, stop reasons, flags. No question, no answer text."""
    rec = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "models": [a.model for a in answers], "tokens": [a.tokens for a in answers],
           "seconds": [round(a.seconds, 2) for a in answers], "stop_reasons": [a.stop_reason for a in answers],
           "flags": [{"hard_violation": f["hard_violation"], "numbers_not_in_handbook_or_message":
                      len(f["numbers_not_in_handbook_or_message"])} for f in (flags(a.raw, user) for a in answers)]}
    line = json.dumps(rec)
    print(line, flush=True)
    p = path or (HERE / CONFIG["log_file"] if CONFIG.get("log_file") else None)
    if p:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    return rec

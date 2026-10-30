# Glossary

**SFT (supervised fine-tuning).** Training a model on example conversations so that it imitates the assistant's
replies.

**Loss masking.** During SFT the model is only graded on the assistant's words, not on the system prompt or the
customer's words. It learns to answer, not to imitate customers. See `docs/masking_example_v1.md`.

**LoRA (low-rank adaptation).** Instead of changing all of a model's weights, train a small add-on, about 0.4 % of
the weights at 14B. It is cheap, and the original model stays untouched.

**rsLoRA (rank-stabilised LoRA).** LoRA with a different scaling of the add-on. It scored higher than plain LoRA in
our pilot and is the default here (ADR-025).

**QLoRA.** LoRA on top of a copy of the model compressed to 4 bits per weight (NF4). It needs much less GPU memory,
at some cost in speed.

**Full fine-tuning.** Training every weight of the model. It is the most flexible option and the most expensive.

**DPO (direct preference optimisation).** Training on pairs of answers, one better and one worse, so that the model
prefers the better kind. It needs no separate reward model.

**SimPO.** A simpler variant of DPO that also needs no reference copy of the model during training.

**GRPO (group relative policy optimisation).** A reinforcement-learning method. The model writes several answers to
each question, they are scored, and the model is pushed towards the above-average ones.

**`<|im_end|>`.** The special token that marks the end of a turn in Qwen's chat format. A model that never produces
it keeps writing, and often invents the customer's next message. In Qwen3 base models this token was never trained,
so LoRA runs here train its row explicitly (ADR-023).

**Wilson CI.** A 95 % confidence interval for a pass rate (k passes out of n). It stays sensible near 0 % and 100 %,
unlike the simple ± formula.

**McNemar test (exact).** Compares two models on the *same* questions. It looks only at the questions where exactly
one of them passed, and asks whether that split could be chance.

**Paired bootstrap.** Estimates the uncertainty of a score difference by resampling the test questions 10,000 times,
keeping the two models paired on each question (and seeds paired), and reading off the middle 95 % of differences.

**Seed.** The random number that fixes data order, initialisation and dropout in a training run. Training the same
recipe with three seeds shows how much of a result is luck.

**Protocol A / B.** The two frozen ways of running the eval. A uses an H200 GPU in bf16 (the main tables). B uses a
free T4 GPU in fp16. Both use greedy decoding, at most 200 new tokens, and the same template and questions.

**T-held.** The 20 eval questions on 10 banking topics deliberately left out of training. They test whether the
model generalises from the handbook instead of recalling memorised answers.

**Red-team.** A set of adversarial prompts written to make the assistant break its rules, for example leaking a
code, following injected instructions or helping fraud. The red-team eval (redteam-v1) is pending.

**Judge.** A separate, larger model used to check text automatically. Here an entailment judge checked whether each
sentence of a rewritten training answer is supported by the handbook. It was validated against hand marks before
use.

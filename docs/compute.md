# Compute

Two tiers share one pipeline ([plan_v3.md](plan_v3.md)). Tier S runs on free
T4 GPUs (Colab / Kaggle) through `notebooks/`; Tier L runs on one shared H200
reached only over SSH from the local machine (host alias `<host>`).

## 1. Tiers and protocols

| | Tier S | Tier L |
|---|---|---|
| Models | Qwen3-1.7B-Base (pilot 0.6B) | Qwen3-14B-Base (fallback 8B); size curve 0.6–14B |
| GPU | T4 16 GB | H200 141 GB |
| Train dtype | fp16 (LoRA), 4-bit nf4 (QLoRA) | bf16 (LoRA, full FT with 8-bit Adam), 4-bit nf4 (QLoRA) |
| Eval protocol | **B** | **A** |

- **Protocol A** = H200, bf16, transformers generate, greedy,
  max_new_tokens 200, eos [151645,151643] — every main-table row.
- **Protocol B** = T4 fp16 (QLoRA/4-bit arms in 4-bit) — the free-compute
  table.

Both protocols use `eval/run_eval.py` with left padding, the frozen chat
template and system prompt; `run.json` records the protocol, GPU, dtype and
batch size of every arm.

## 2. H200 workspace

The H200 is shared with the GTD project, which has priority until its queue
finishes. Three paths are used on the server and nothing else:
`<workspace>/chinor/**`, the shared Hugging Face cache
`<workspace>/hf` and the GPU lock `<workspace>/GPU_LOCK`.
Everything else under `<workspace>/`, including
`<workspace>/gtd`, is off limits.

```
<workspace>/
├── GPU_LOCK   shared GPU lock, one line "project pid started_at" (§5)
├── hf/        HF_HOME shared with GTD: weights used by both projects are downloaded once
└── chinor/    (chmod 700)
    ├── repo/      working tree synced from the local machine (no .git)
    ├── runs/      one folder per launched run: log.txt, pid, run.json, exit_code
    ├── results/   one folder per run: eval outputs (<arm>/answers.jsonl, run.json), data, adapters
    ├── logs/      install and check logs
    ├── venv/      training/eval venv (system site packages = the server's torch), scripts/h200/install.sh
    ├── venv-gen/  generation venv (system site packages = the server's torch), scripts/h200/install_gen.sh
    └── .cache/    pip / triton / vllm / torch caches (env.sh); nothing is written under $HOME,
                   which is shared with other projects and sessions on the same account
```

### Storage budget

Sizes are the Hub repository sizes (bf16 safetensors) and land in the shared
cache; a model GTD has already downloaded costs nothing extra.

| Item | GB |
|---|---|
| Qwen3-0.6B / 1.7B / 4B / 8B / 14B-Base | 1.2 + 3.4 + 8.0 + 16.4 + 29.5 = 58.5 |
| Qwen3-32B (generator) | 65.5 |
| gemma-4-31B-it (judge; bf16 weights ≈ 62, Hub repo larger) | ≈ 62 |
| Llama-3.3-70B-Instruct fp8 (judge fallback, only if needed) | ≈ 70 |
| **Shared cache total** (without / with fallback judge) | **≈ 186 / 256** |
| chinor/results: LoRA adapters (≈ 0.1–0.5 GB each), eval outputs | < 20 |
| chinor/results: 14B full-FT checkpoints (≈ 30 GB weights each; optimizer state only for the latest) | ≈ 90 per seed while training, 30 kept until uploaded |
| **chinor total, peak** | **≈ 110** |

Full-FT checkpoints are deleted (after confirmation) once uploaded; at most
one full-FT run's checkpoints exist at a time.

There is no git repository, git identity, GitHub token or assistant
configuration on the server. The commit a run was launched from is the
`COMMIT` file that `sync_up.sh` writes into `repo/` (HEAD, with `-dirty`
appended when the local tree had uncommitted changes); `run_eval.py` and
`launch.sh` read it.

## 3. Sync workflow

All commits and pushes happen on the local machine.

1. Commit locally.
2. `bash scripts/h200/sync_up.sh` — writes `COMMIT` and copies the working
   tree to `<host>:<workspace>/chinor/repo/`, skipping everything
   in `.rsync-exclude` (`.git`, `.venv`, `.env`, eval outputs, raw results,
   weights, notebooks, assistant configuration). It uses `rsync` when the
   local shell has it and a `tar | ssh` stream otherwise (Git Bash ships
   without rsync). It never deletes on the server; removing stale remote
   files is a separate command that is shown and confirmed first.
3. Launch on the server with `launch.sh` (§5).
4. `bash scripts/h200/sync_down.sh <run_name>` — copies
   `results/<run_name>/<arm>/` into `eval/outputs/<arm>/` and
   `runs/<run_name>/{log.txt,run.json}` into `results/raw/<run_name>/`.
5. Score and summarise locally, commit, upload adapters, report. Nothing
   stays only on the H200.

## 4. Tokens

- **GitHub:** no GitHub token on the server, ever. The server never clones,
  pulls or pushes.
- **Hugging Face:** a fine-grained token with write access to the project's
  model repositories only, 7-day expiry, kept in the local shell. It is
  passed only as an environment prefix on the single upload command:

  ```
  HF_TOKEN="$HF_TOKEN" bash scripts/h200/upload_adapter.sh <run_name> <hf_repo>
  ```

  Run locally, `upload_adapter.sh` refuses when the variable is unset,
  then writes the token to the SSH session's stdin (never to the remote
  command line, where other users could see it in `ps`); the remote half
  of the same script reads it into the environment of one
  `hf upload` (`huggingface-cli upload` on older hubs) process and nothing
  else. The token is never echoed, logged, written to `run.json`,
  notebooks, rc files or `.git/config`, and is never stored on the server.
  Public model downloads need no token.

## 5. Launch, monitor, resume

- **GPU lock.** `<workspace>/GPU_LOCK` is a one-line file
  `project pid started_at`. `launch.sh` takes it (project `chinor`) before
  every run: it refuses to start while a live PID holds it and prints who
  holds it and since when; it removes the lock only when its PID is dead;
  the run's wrapper process (the PID in `runs/<name>/pid`) holds the lock
  and releases it when it exits, including on SIGTERM. A lock held by a live
  PID of GTD is never edited or deleted. Large vLLM jobs (the 32B
  generation) start only when the lock is free. CPU/network-only jobs
  (weight downloads) run with `NO_GPU_LOCK=1`. Tested with dummy runners
  in `scripts/h200/test_gpu_lock.sh` (temporary lock file, never the real
  one).
- **Launch.** Every run goes through
  `ssh <host> 'bash <workspace>/chinor/repo/scripts/h200/launch.sh <name> <cmd...>'`.
  `launch.sh` sources `env.sh`, creates `runs/<name>/`, starts the command
  under `nohup setsid` (it survives the SSH session ending), writes `pid`,
  `log.txt` and `run.json` (COMMIT, config hash, seed, GPU, dtype, start
  time) and appends `exit_code` and the end time when the command finishes.
  Nothing is run in the foreground of an SSH session.
- **Monitor.** `ssh <host> 'bash <workspace>/chinor/repo/scripts/h200/status.sh'`
  shows, per run, whether its PID is alive, the exit code if finished, the
  last 20 log lines, and an `nvidia-smi` summary.
- **Stop.** Only PIDs recorded in `runs/*/pid` may be killed, and only after
  the exact command has been shown and confirmed. `pkill`, `killall` and
  killing other users' processes are never used.
- **Resume.** `launch.sh` refuses a name whose PID is alive, and refuses an
  existing finished run unless `RESUME=1` is set (confirmed first, because
  it appends to the log and may overwrite outputs). Training scripts write
  checkpoints to `results/<name>/ckpt/` and take `--resume`, so a resumed
  run continues from the latest checkpoint; eval runs are short and are
  simply relaunched under a new name.

- **Queues and isolation.** GPU jobs run through `scripts/h200/queue.sh` (job lists) or `run_matrix.sh`
  (training runs), one `launch.sh` run per job, so the lock is released between jobs. Before every launch:
  `GPU_WANTED` absent and `GPU_LOCK` free (else wait, re-check every 60 s), cutoff not passed, ≥ 60 GB free,
  and (in `launch.sh`, before the lock) every model file of the revision present in `HF_HOME`; a job whose
  weights are not ready does not take the lock, and the queue runs the next ready job. Downloads run only as
  CPU jobs (`NO_GPU_LOCK=1`). At start a queue freezes itself: `scripts/h200/` and the job list are copied to
  `runs/_queues/<queue_name>/` (local, git-ignored; `queue.log` records the copy), the launch-side scripts to
  `$CHINOR/runs/_queues/<queue_name>/`, job commands are rewritten to the frozen server copy, and the queue runs
  only from the frozen copies. Editing the repo's scripts never reaches a running queue. Waiter scripts never
  start queues; a queue is started directly, after the previous one has ended. Reason (night of 2026-10-28/29):
  (1) `queue.sh` was edited while a queue was running it and the queue broke after its last job (the post-job
  sync of the judge validation was lost and done by hand); (2) a waiter that was to start the next queue
  matched its own command line, concluded the old queue was alive, and never started it (GPU idle); (3)
  stopping that waiter left its child queue alive, so two queues ran side by side for about 30 s (unique run
  names prevented duplicate launches). Tested in `scripts/h200/test_queue.sh` (a queue keeps running from its
  frozen copy while the repo's `queue_lib.sh` is overwritten).

## 6. Server rules

Allowed paths: `<workspace>/chinor/**`, `<workspace>/hf`
and `<workspace>/GPU_LOCK`. Not used: `pkill`,
`killall`, `kill` of foreign PIDs, `rm -rf` outside the workspace, docker,
conda environment changes, `pip install` of torch / torchvision /
torchaudio or of anything whose resolver plan would reinstall them,
`pip install --user` and any write to `~/.local` (the account is shared
with other projects and sessions), edits to system files, `chmod` outside
the workspace. Every install goes into a venv inside the workspace created
with `python -m venv --system-site-packages` (the server's torch stays the
only torch): `chinor/venv` for training and evaluation (`install.sh`),
`chinor/venv-gen` for generation with vLLM (`install_gen.sh`), each after a
dry-run that aborts on torch / torchvision / torchaudio / triton /
`nvidia-*`. Inside the venvs the image's pip constraint file is replaced by
its torch-stack pins only (`venv_lib.sh`). `PYTHONNOUSERSITE=1` is set in
`env.sh` and `launch.sh` for every job, so the user site is never read. Destructive
commands (`rm`, overwriting checkpoints, `rsync --delete`, killing an own
run) are shown and confirmed before they run.

## 7. Checklists

**Start of session**

1. Start the H200 session; save the key to `~/.ssh/id_container`.
2. `bash scripts/h200/set_port.sh <port> <proxy host>` — both change per session and live only in `~/.ssh/config`.
3. `bash scripts/h200/check.sh` — GPU, torch/CUDA/bf16, reachability of
   GitHub / HF / PyPI, free disk, user-site, tmux, GPU lock holder, user
   packages.
4. `ssh <host> 'bash <workspace>/chinor/repo/scripts/h200/status.sh'` —
   any run left over from the last session?
5. `git pull` locally, commit, `bash scripts/h200/sync_up.sh`.

**End of session**

1. `status.sh`: every run finished (or deliberately left running and noted).
2. `sync_down.sh <run>` for every finished run; score, summarise, commit,
   push.
3. Upload adapters with `upload_adapter.sh`; check they are on the Hub.
4. Confirm nothing exists only on the server (`results/<run>/` all synced).
5. Let the HF token expire or revoke it if the session is the last one of
   the week.

## Disk: shared-cache deletion of Qwen/Qwen3-32B (2026-10-29)

On the author's instruction, the shared HF cache copy of `Qwen/Qwen3-32B` (public, re-downloadable; used only for
the finished C1 rewrite generation) was deleted to make room for the full-FT diagnosis run (ADR-030, ADR-027 disk
rule). Checks before deleting: no process had it open, no running process mentioned it, and no queued job, config
or frozen queue of either project (GTD's tree read-only) referenced it. Deleted: only
`<workspace>/hf/hub/models--Qwen--Qwen3-32B` (62 GB). `google/gemma-4-31B-it`, every base model and all
trained weights were kept.

| Time (KST) | Free on <workspace> (NFS, 1.9 TB) |
|---|---|
| 14:38, before | 95 GB |
| 14:38, just after | 95 GB (NFS had not yet reclaimed the space) |
| ~14:55 | 156 GB |

## Disk: full-FT lr 1e-5 seed-1 weights deleted (2026-10-29)

On the author's instruction (evaluated, SHA-256 manifest `944e398c…` recorded in
`results/runs/l14b_full-s1/train/run.json`; the lr 1e-5 setting is superseded by lr 2e-5, ADR-030), only
`<workspace>/chinor/results/l14b_full-s1/train/model` (29.5 GB, 28 GiB) was deleted; that run's
`train/run.json`, `loss.csv` and eval outputs were kept. The weights of `l14b_full-s0` (lr 1e-5) and
`l14b_full_lr2e5-s0` were kept. Free space was 129 GB just before and just after (NFS reclaims with a delay), enough
for the seed-1 lr 2e-5 run (ADR-027: ≥ 120 GB), which started at 18:44 KST.

## sft-merged (2026-10-29)

`train/merge_sft.py`: Qwen3-14B-Base + `l14b_sft_rslora_tok-s0-v1.2` adapter (sha256 3f3707fd…f60003f, incl. the
trained `<|im_start|>` / `<|im_end|>` rows), bf16 on CPU → `$CHINOR/results/sft-merged-l14b-v1.2-s0/model`. Checks:
token rows equal the adapter's and differ from the base; same top-5; max prob diff 0.00149 (max logit diff 0.25).
manifest_sha256 **e4d24cc5e588182a0142bfca68f14aae5027a664b1caa994c5394d4a923003b0** (merge.json). Reference model of
DPO = this model with the adapter disabled. Deleted after the last preference job (closing plan).

## Closing clean-up (2026-10-29, 22:31 KST)

After the last preference job was synced and hashed (`results/model_sha256.tsv`): deleted sft-merged (28 GB), the
gemma-4-31B-it cache (59 GB; its blobs were linked by no other model), full-FT lr 1e-5 seed 0 and lr 2e-5 seed 1
weights (28 GB each), every remaining checkpoint (0.6 GB) and `runs/_scratch` (3.3 GB). Kept: full-FT lr 2e-5 seed 0
weights and all 55 adapters. Free disk on <workspace>: **96 GB before, 241 GB after** (read 90 s later; NFS
lag). No Chinor process holds the GPU lock.

Preference stage GPU time: sampling 0.58 h; 6 runs × 7–8 min incl. both evals (DPO 0.10 GPU-h, SimPO 0.08 GPU-h per seed).

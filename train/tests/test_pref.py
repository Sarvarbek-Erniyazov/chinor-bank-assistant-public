"""train/pref.py losses and log-prob masking against the reference formulas on toy tensors."""
import math
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pref  # noqa: E402

sig = lambda x: 1 / (1 + math.exp(-x))


def test_dpo_formula():
    pc, pr, rc, rr = torch.tensor([-10.0, -5.0]), torch.tensor([-12.0, -4.0]), torch.tensor([-11.0, -5.0]), torch.tensor([-11.0, -5.0])
    loss, cw, rw = pref.dpo_loss(pc, pr, rc, rr, beta=0.1)
    for i in range(2):
        z = 0.1 * ((pc[i] - rc[i]) - (pr[i] - rr[i])).item()
        assert abs(loss[i].item() + math.log(sig(z))) < 1e-6
    assert torch.allclose(cw, 0.1 * (pc - rc)) and torch.allclose(rw, 0.1 * (pr - rr))
    # policy == reference -> loss log 2
    l0, _, _ = pref.dpo_loss(rc, rr, rc, rr)
    assert torch.allclose(l0, torch.full_like(l0, math.log(2)))


def test_simpo_formula():
    pc, pr, lc, lr = torch.tensor([-20.0]), torch.tensor([-30.0]), torch.tensor([10.0]), torch.tensor([12.0])
    loss, cw, rw = pref.simpo_loss(pc, pr, lc, lr, beta=2.0, gamma=1.0)
    z = 2.0 * -20 / 10 - 2.0 * -30 / 12 - 1.0
    assert abs(loss.item() + math.log(sig(z))) < 1e-6 and abs(cw.item() + 4.0) < 1e-6


def test_seq_logps_masks_and_shifts():
    torch.manual_seed(0)
    logits = torch.randn(1, 5, 7)
    labels = torch.tensor([[-100, -100, 3, 4, -100]])
    lp, n = pref.seq_logps(logits, labels)
    ls = torch.log_softmax(logits, -1)
    assert n.item() == 2 and abs(lp.item() - (ls[0, 1, 3] + ls[0, 2, 4]).item()) < 1e-5


def test_lr_schedule():
    peak = 1e-5
    assert abs(pref.lr_at(0, 100, 10, peak) - peak / 10) < 1e-12
    assert abs(pref.lr_at(10, 100, 10, peak) - peak) < 1e-12
    assert pref.lr_at(99, 100, 10, peak) < 0.01 * peak


def test_pref_configs():
    import yaml
    for p in sorted((Path(__file__).resolve().parents[1] / "configs").glob("pref_*.yaml")):
        cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
        assert cfg["loss"] in ("dpo", "simpo") and cfg["max_length"] == 1024, p.name
        assert cfg["per_device_train_batch_size"] * cfg["gradient_accumulation_steps"] == 16, p.name
        assert cfg["learning_rate"] == (5e-6 if p.stem == "pref_dpo_v2" else 1e-5) and cfg["num_train_epochs"] == 2 and cfg["lora"]["r"] == 16, p.name
        assert (cfg["beta"], cfg.get("gamma")) == ((0.1, None) if cfg["loss"] == "dpo" else (2.0, 1.0)), p.name


def test_sft_alpha_zero_is_pure_dpo_and_adds_chosen_nll():
    pc, pr, rc, rr = torch.tensor([-10.0, -6.0]), torch.tensor([-12.0, -4.0]), torch.tensor([-11.0, -5.0]), torch.tensor([-11.0, -5.0])
    lc = torch.tensor([5.0, 3.0])
    loss, _, _ = pref.dpo_loss(pc, pr, rc, rr, beta=0.1)
    assert torch.equal(pref.with_sft(loss, pc, lc, 0.0), loss)
    assert torch.allclose(pref.with_sft(loss, pc, lc, 0.2), loss + 0.2 * torch.tensor([2.0, 2.0]))


def test_step0_policy_equals_reference():
    rc, rr = torch.tensor([-11.0, -5.0, -30.0]), torch.tensor([-9.0, -7.0, -2.0])
    loss, cw, rw = pref.dpo_loss(rc, rr, rc, rr, beta=0.1)
    assert abs(loss.mean().item() - math.log(2)) < 1e-6 and torch.all(cw == 0) and torch.all(rw == 0)
    assert pref.step0_ok(loss.mean().item()) and pref.step0_ok(0.70) and not pref.step0_ok(0.71)

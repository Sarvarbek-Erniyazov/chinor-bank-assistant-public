"""NumPy <-> torch bridge test for a venv on the H200 (run by install.sh / install_gen.sh).

python scripts/h200/bridge_test.py --out <json> [--datasets]
Checks torch.from_numpy, tensor.numpy() and torch.tensor(ndarray); with --datasets also a datasets
Dataset.map + set_format("torch") round trip. Exit 1 if any check fails.
"""
import argparse
import json
import sys

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--datasets", action="store_true")
a = ap.parse_args()
res = {}


def check(name, f):
    try:
        f()
        res[name] = "ok"
    except Exception as e:  # report every failure, not only the first
        res[name] = f"FAIL {type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}"


import numpy as np  # noqa: E402
import torch  # noqa: E402
res["versions"] = {"numpy": np.__version__, "torch": torch.__version__}
check("torch.from_numpy", lambda: torch.from_numpy(np.arange(3)).sum().item())
check("tensor.numpy()", lambda: torch.arange(3).numpy().sum())
check("torch.tensor(ndarray)", lambda: torch.tensor(np.arange(3)).sum().item())
if a.datasets:
    def roundtrip():
        from datasets import Dataset
        ds = Dataset.from_list([{"input_ids": [1, 2, 3]}, {"input_ids": [4, 5]}]).map(lambda x: {"n": len(x["input_ids"])})
        t = ds.with_format("torch")[0]["input_ids"]
        assert isinstance(t, torch.Tensor) and t.tolist() == [1, 2, 3] and ds[1]["n"] == 2
    check("datasets map + set_format(torch)", roundtrip)
ok = all(v == "ok" for k, v in res.items() if k != "versions")
res["pass"] = ok
json.dump(res, open(a.out, "w"), indent=2)
print(json.dumps(res, indent=2))
sys.exit(0 if ok else 1)

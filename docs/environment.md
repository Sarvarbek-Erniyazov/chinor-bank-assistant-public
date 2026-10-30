# Environment

## Local (CPU)

Filled from `pip freeze` after the venv was created; see the bottom of this
file. Platform: Windows 11, Git Bash, no CUDA.

## Colab (GPU)

`requirements-gpu.txt`; runtime: T4 (16 GB), fp16. torch is not pinned: the
Colab image's own torch is used, and torchvision/torchaudio are uninstalled
(a pinned torch replaced the image's build and broke its torchvision). The
notebook writes the resolved versions into `eval/outputs/<arm>/run.json`.

## Resolved local versions

```
Python 3.11.9 (py launcher -3.11), Windows 11, torch CPU wheel
accelerate==1.15.0
datasets==5.1.0
huggingface_hub==2.3.0
Jinja2==3.1.6
nbformat==5.11.1
numpy==2.4.6
pytest==9.1.1
PyYAML==6.0.3
RapidFuzz==3.14.6
safetensors==0.8.0
scipy==1.17.1
tokenizers==0.23.3
torch==2.14.1+cpu
transformers==5.21.0
```

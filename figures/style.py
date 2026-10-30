"""Shared figure style: Okabe–Ito method colours, cividis heatmaps, DejaVu Sans 8/9 pt, light and dark themes.

Data colours are identical in both themes; only background, text, grid and edge tokens differ. Output is
deterministic: fixed SVG hash salt, no dates or software stamps in SVG / PDF / PNG metadata.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

WIDTH_1COL, WIDTH_2COL = 3.4, 7.0  # inches
DPI = 300
HASHSALT = "chinor-figures"
# method → colour (Okabe–Ito). GRPO yellow is drawn with a dark edge (EDGE_FOR) in both themes.
METHOD_COLOURS = {
    "base": "#999999", "SFT-LoRA": "#0072B2", "rsLoRA": "#56B4E9", "QLoRA": "#009E73", "full FT": "#E69F00",
    "DPO": "#D55E00", "SimPO": "#CC79A7", "GRPO": "#F0E442",
}
METHOD_COLOURS["instruct (reference)"] = METHOD_COLOURS["base"]  # drawn hollow (reference, not a pipeline arm)
METHOD_COLOURS["DoRA"] = METHOD_COLOURS["SFT-LoRA"]  # pilot only, drawn hatched
EDGE_FOR = {"GRPO": "#5A5000"}
HEATMAP = "cividis"
THEMES = {
    "light": {"bg": "#FFFFFF", "text": "#1A1A1A", "muted": "#5C5C5C", "grid": "#E3E3E3", "edge": "#FFFFFF", "axis": "#8A8A8A"},
    "dark": {"bg": "#16181C", "text": "#ECECEC", "muted": "#A8A8A8", "grid": "#33363C", "edge": "#16181C", "axis": "#6E7178"},
}


def colour(method: str) -> str:
    return METHOD_COLOURS.get(method, METHOD_COLOURS["base"])


def edge(method: str, theme: str) -> str:
    """Edge for a filled mark: a surface-coloured gap between neighbours, dark for the yellow GRPO fill."""
    return EDGE_FOR.get(method, THEMES[theme]["edge"])


def rc(theme: str) -> dict:
    t = THEMES[theme]
    return {
        "font.family": "DejaVu Sans", "font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8, "xtick.labelsize": 8,
        "ytick.labelsize": 8, "legend.fontsize": 8, "figure.titlesize": 9,
        "figure.facecolor": t["bg"], "axes.facecolor": t["bg"], "savefig.facecolor": t["bg"], "savefig.edgecolor": t["bg"],
        "text.color": t["text"], "axes.labelcolor": t["text"], "axes.titlecolor": t["text"], "xtick.color": t["muted"],
        "ytick.color": t["muted"], "axes.edgecolor": t["axis"], "axes.grid": True, "grid.color": t["grid"],
        "grid.linewidth": 0.6, "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
        "legend.frameon": False, "lines.linewidth": 1.5, "lines.markersize": 5, "patch.linewidth": 0.8,
        "svg.hashsalt": HASHSALT, "svg.fonttype": "path", "pdf.fonttype": 42, "image.cmap": HEATMAP,
    }


@contextmanager
def themed(theme: str):
    with plt.rc_context(rc(theme)):
        yield THEMES[theme]


def save(fig, out_dir: Path, fid: str, theme: str) -> list[Path]:
    """figures/<id>_<theme>.{png,svg,pdf}, metadata stripped so reruns are byte-stable."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext, meta in [("svg", {"Date": None, "Creator": None}), ("pdf", {"CreationDate": None, "ModDate": None, "Creator": None, "Producer": None}),
                      ("png", {"Software": None})]:
        p = out_dir / f"{fid}_{theme}.{ext}"
        with plt.rc_context({"svg.hashsalt": HASHSALT}):  # the theme context has closed by the time we save
            fig.savefig(p, format=ext, dpi=DPI, metadata=meta, bbox_inches="tight", pad_inches=0.03)
        paths.append(p)
    plt.close(fig)
    return paths

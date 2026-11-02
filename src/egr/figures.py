"""Figures from the result tables, in a light and a dark version each."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import pandas as pd
from matplotlib.figure import Figure

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from egr import config

SERIES = {
    "combined": "#2a78d6",
    "rules": "#eb6834",
    "plausibility": "#1baf7a",
    "nothing": "#898781",
}
SERIES_DARK = {
    "combined": "#3987e5",
    "rules": "#d95926",
    "plausibility": "#199e70",
    "nothing": "#898781",
}
LABELS = {
    "combined": "combined (rules, then plausibility)",
    "rules": "rules only",
    "plausibility": "plausibility only",
    "nothing": "flag nothing",
}
TYPE_LABELS = {
    "sign_flip": "sign flip",
    "scale_slip": "scale slip",
    "digit_transposition": "digit transposition",
    "copy_forward": "copy-forward",
    "cross_company_swap": "cross-company swap",
}
THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "muted": "#52514e",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
    },
    "dark": {
        "surface": "#1a1a19",
        "ink": "#f0efec",
        "muted": "#c3c2b7",
        "grid": "#2c2c2a",
        "axis": "#383835",
    },
}


def _style(theme: str) -> dict[str, str]:
    t = THEMES[theme]
    plt.rcParams.update(
        {
            "figure.facecolor": t["surface"],
            "axes.facecolor": t["surface"],
            "savefig.facecolor": t["surface"],
            "text.color": t["ink"],
            "axes.labelcolor": t["muted"],
            "xtick.color": t["muted"],
            "ytick.color": t["muted"],
            "axes.edgecolor": t["axis"],
            "grid.color": t["grid"],
            "font.family": "sans-serif",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.grid.axis": "y",
            "grid.linewidth": 0.6,
            "legend.frameon": False,
        }
    )
    return t


def _colors(theme: str) -> dict[str, str]:
    return SERIES_DARK if theme == "dark" else SERIES


def _save(fig: Figure, name: str, theme: str, out_dir: Path) -> Path:
    path = out_dir / (f"{name}.png" if theme == "light" else f"{name}_dark.png")
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


def budget_figure(metrics: pd.DataFrame, theme: str, out_dir: Path) -> Path:
    """Errors caught per budgeted flag and recall against the budget, primary error rate."""
    t = _style(theme)
    colors = _colors(theme)
    data = metrics[metrics["error_rate"] == config.ERROR_RATE]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
    for ax, metric, title in (
        (axes[0], "errors_per_budgeted_flag", "Injected errors caught per budgeted flag"),
        (axes[1], "recall", "Recall of injected errors"),
    ):
        for det in ("combined", "plausibility", "rules"):
            d = data[data["detector"] == det].sort_values("budget_per_1000")
            ax.plot(
                d["budget_per_1000"],
                d[metric],
                color=colors[det],
                lw=2,
                marker="o",
                ms=5,
                label=LABELS[det],
            )
            ax.fill_between(
                d["budget_per_1000"],
                d[f"{metric}_lo"],
                d[f"{metric}_hi"],
                color=colors[det],
                alpha=0.12,
                lw=0,
            )
            last = d.iloc[-1]
            ax.annotate(
                f"{last[metric]:.2f}",
                (last["budget_per_1000"], last[metric]),
                textcoords="offset points",
                xytext=(6, 0),
                va="center",
                fontsize=9,
                color=t["ink"],
            )
        ax.set_xscale("log")
        ax.set_xticks(list(config.BUDGETS_PER_1000))
        ax.set_xticklabels([str(b) for b in config.BUDGETS_PER_1000])
        ax.set_xlabel("flags per 1,000 held-out cells")
        ax.set_title(title, loc="left", fontsize=11, color=t["ink"])
        ax.set_ylim(bottom=0)
    axes[0].legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    return _save(fig, "budget_comparison", theme, out_dir)


def type_figure(by_type: pd.DataFrame, theme: str, out_dir: Path) -> Path:
    """Recall by error type at the primary budget, grouped bars."""
    t = _style(theme)
    colors = _colors(theme)
    data = by_type[
        (by_type["error_rate"] == config.ERROR_RATE)
        & (by_type["budget_per_1000"] == config.BUDGET_PRIMARY)
    ]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    types = list(config.ERROR_TYPES)
    dets = ("combined", "plausibility", "rules")
    width = 0.26
    for j, det in enumerate(dets):
        d = data[data["detector"] == det].set_index("error_type").reindex(types)
        xs = [i + (j - 1) * width for i in range(len(types))]
        ax.bar(xs, d["recall"], width=width - 0.03, color=colors[det], label=LABELS[det])
        for x, v in zip(xs, d["recall"], strict=True):
            ax.annotate(
                f"{v:.2f}",
                (x, v),
                textcoords="offset points",
                xytext=(0, 3),
                ha="center",
                fontsize=8,
                color=t["ink"],
            )
    ax.set_xticks(range(len(types)))
    ax.set_xticklabels([TYPE_LABELS[k] for k in types])
    ax.set_ylabel("recall at the primary budget")
    ax.set_ylim(0, 1)
    ax.set_title(
        f"Recall by error type at {config.BUDGET_PRIMARY} flags per 1,000 cells",
        loc="left",
        fontsize=11,
        color=t["ink"],
    )
    ax.legend(fontsize=9)
    fig.tight_layout()
    return _save(fig, "recall_by_type", theme, out_dir)


def false_flag_figure(ffr: pd.DataFrame, theme: str, out_dir: Path) -> Path:
    """Achieved false-flag rate against the target, clean calibration."""
    t = _style(theme)
    colors = _colors(theme)
    data = ffr[ffr["calibration"].str.startswith("clean")]
    fig, ax = plt.subplots(figsize=(4.8, 3.6))
    ax.plot([0, 0.25], [0, 0.25], color=t["axis"], lw=1, ls="--", label="target")
    for det in ("plausibility", "combined"):
        d = data[data["detector"] == det].sort_values("target")
        ax.errorbar(
            d["target"],
            d["achieved_false_flag_rate"],
            yerr=[d["achieved_false_flag_rate"] - d["lo"], d["hi"] - d["achieved_false_flag_rate"]],
            color=colors[det],
            marker="o",
            ms=6,
            lw=2,
            capsize=3,
            label=LABELS[det],
        )
    ax.set_xlabel("Benjamini-Hochberg target")
    ax.set_ylabel("achieved false-flag rate")
    ax.set_xticks(list(config.BH_TARGETS))
    ax.set_xlim(0, 0.25)
    ax.set_ylim(bottom=0)
    ax.set_title("False-flag rate on held-out companies", loc="left", fontsize=11, color=t["ink"])
    ax.legend(fontsize=9, loc="upper left")
    fig.tight_layout()
    return _save(fig, "false_flag_rate", theme, out_dir)


def faithfulness_figure(faith: pd.DataFrame, theme: str, out_dir: Path) -> Path | None:
    """Verified share of claims and rejection rate per text variant."""
    t = _style(theme)
    data = faith[faith["run"] == True]  # noqa: E712
    if data.empty:
        return None
    labels = {
        "template": "template",
        "llm_evidence": "model, evidence record",
        "llm_raw": "model, raw data",
    }
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.2))
    for ax, col, title in (
        (axes[0], "claims_verified_share", "Share of claims verified against the evidence"),
        (axes[1], "rejection_rate", "Texts rejected by the checker"),
    ):
        ys = range(len(data))
        ax.barh(list(ys), data[col], color=_colors(theme)["combined"], height=0.5)
        for y, v in zip(ys, data[col], strict=True):
            ax.annotate(
                f"{v:.2f}",
                (v, y),
                textcoords="offset points",
                xytext=(4, 0),
                va="center",
                fontsize=9,
                color=t["ink"],
            )
        ax.set_yticks(list(ys))
        ax.set_yticklabels([labels[v] for v in data["variant"]])
        ax.set_xlim(0, 1.15)
        ax.invert_yaxis()
        ax.grid(axis="x")
        ax.grid(False, axis="y")
        ax.set_title(title, loc="left", fontsize=10, color=t["ink"])
    fig.tight_layout()
    return _save(fig, "faithfulness", theme, out_dir)


def make_figures(
    tables_dir: Path = config.TABLES_DIR, out_dir: Path = config.FIGURES_DIR
) -> list[Path]:
    """All figures in both themes."""
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics = pd.read_csv(tables_dir / "budget_metrics.csv")
    by_type = pd.read_csv(tables_dir / "recall_by_type.csv")
    ffr = pd.read_csv(tables_dir / "false_flag_rate.csv")
    faith_path = tables_dir / "faithfulness.csv"
    faith = pd.read_csv(faith_path) if faith_path.exists() else pd.DataFrame(columns=["run"])
    paths: list[Path] = []
    for theme in ("light", "dark"):
        paths.append(budget_figure(metrics, theme, out_dir))
        paths.append(type_figure(by_type, theme, out_dir))
        paths.append(false_flag_figure(ffr, theme, out_dir))
        p = faithfulness_figure(faith, theme, out_dir)
        if p is not None:
            paths.append(p)
    return paths

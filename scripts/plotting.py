"""Estilo de figura unico para todo o projeto (paleta validada, marcas finas)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#8a8880"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
YELLOW = "#eda100"
RED = "#e34948"
VIOLET = "#4a3aa7"


def apply_style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.family": "DejaVu Sans", "font.size": 10,
        "text.color": INK, "axes.labelcolor": INK2, "axes.titlecolor": INK,
        "axes.edgecolor": "#d8d6cf", "axes.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False,
        "xtick.color": INK2, "ytick.color": INK2,
        "xtick.labelsize": 9, "ytick.labelsize": 9,
        "grid.color": "#e7e5de", "grid.linewidth": 0.8,
        "legend.frameon": False, "legend.fontsize": 9,
        "lines.linewidth": 2.0, "figure.dpi": 130,
    })


def level_bands(ax, sp=50.0, lo_lo=20.0, hi_hi=80.0, lo=35.0, hi=65.0,
                env=(30.0, 70.0), label=True):
    """Faixas de trip (protecao), alarme e envelope (governor)."""
    ax.axhspan(-20, lo_lo, color=RED, alpha=0.10, lw=0)
    ax.axhspan(hi_hi, 120, color=RED, alpha=0.10, lw=0)
    ax.axhline(lo_lo, color=RED, lw=1.2, ls="-")
    ax.axhline(hi_hi, color=RED, lw=1.2, ls="-")
    ax.axhline(lo, color=YELLOW, lw=1.0, ls=":")
    ax.axhline(hi, color=YELLOW, lw=1.0, ls=":")
    ax.axhline(env[0], color=VIOLET, lw=1.0, ls="--", alpha=0.8)
    ax.axhline(env[1], color=VIOLET, lw=1.0, ls="--", alpha=0.8)
    ax.axhline(sp, color=MUTED, lw=0.9, ls="-", alpha=0.7)
    if label:
        ax.text(0.995, hi_hi + 1.5, "TRIP HI-HI (ESFAS)", color=RED, fontsize=8,
                ha="right", va="bottom", transform=ax.get_yaxis_transform())
        ax.text(0.995, lo_lo - 1.5, "TRIP LO-LO (ESFAS)", color=RED, fontsize=8,
                ha="right", va="top", transform=ax.get_yaxis_transform())
        ax.text(0.005, env[1] + 1.0, "envelope do governor", color=VIOLET,
                fontsize=8, ha="left", va="bottom",
                transform=ax.get_yaxis_transform())


def finish(fig, path):
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path

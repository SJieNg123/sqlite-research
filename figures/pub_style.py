"""The paper figures' house style: the scientific-figure-making (figures4papers) skill.

Import AFTER plot_utils, whose own rcParams are applied at import time, then call
apply(). Adopted for Figures 1, 13, 14, 16 and 19 so that every figure in the
paper shares one type scale, one spine treatment and one semantic palette.
"""
import matplotlib.pyplot as plt

# The skill's semantic palette: blues for our method, greens for positive variants,
# reds for baselines and contrasts, neutrals for reference. NEUTRAL_DARK stands in
# for NEUTRAL wherever a mark is a thin line, which the pale grey is too light for.
PALETTE = {
    "blue_main": "#0F4D92", "blue_secondary": "#3775BA",
    "green_1": "#DDF3DE", "green_2": "#AADCA9", "green_3": "#8BCF8B",
    "red_1": "#F6CFCB", "red_2": "#E9A6A1", "red_strong": "#B64342",
    "neutral": "#CFCECE", "neutral_dark": "#767676", "ink": "#272727",
    "teal": "#42949E", "violet": "#9A4D8E",
}


def apply(font_size=15, axes_linewidth=2):
    plt.rcParams.update({
        "font.family": "DejaVu Sans",  # the skill's fallback; Arial/Helvetica not installed
        "font.size": font_size,
        # plot_utils pins these to absolute sizes (10/12/9 pt), which font.size does
        # not reach, so they must be set here or axis titles stay at 10 pt.
        "axes.labelsize": font_size - 1,
        "axes.titlesize": font_size,
        "legend.fontsize": font_size - 2,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": axes_linewidth,
        "axes.grid": False,
        "legend.frameon": False,
        "svg.fonttype": "none",
        "savefig.dpi": 300,
    })

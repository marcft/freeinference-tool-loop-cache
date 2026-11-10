"""Draws figure1.png from around.csv, which numbers.py writes."""
import csv

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 9,
    "axes.linewidth": 0.6,
    "xtick.direction": "in",
    "ytick.direction": "in",
})

rows = list(csv.DictReader(open("around.csv")))
x = [int(r["steps_from_the_losing_step"]) for r in rows]
median = [float(r["median_pct_of_prompt_cached"]) for r in rows]
below = [m - float(r["lower_quartile"]) for m, r in zip(median, rows)]
above = [float(r["upper_quartile"]) - m for m, r in zip(median, rows)]

fig, ax = plt.subplots(figsize=(3.5, 2.3), dpi=300)
ax.errorbar(x, median, yerr=[below, above], color="black", linewidth=1, marker="o", markersize=3.5,
            capsize=2.5, capthick=0.6, elinewidth=0.6)
ax.set_xticks(x)
ax.set_xticklabels(["-3", "-2", "-1", "0", "+1", "+2", "+3"])
ax.set_yticks([0, 20, 40, 60, 80, 100])
ax.set_ylim(-5, 105)
ax.set_xlim(-3.4, 3.4)
ax.grid(axis="y", linestyle=":", linewidth=0.5, color="0.7")
ax.set_axisbelow(True)
ax.tick_params(top=True, right=True, length=3, width=0.6)
ax.set_xlabel("Step relative to the step that loses its cache")
ax.set_ylabel("Prompt served from cache (%)")
fig.tight_layout(pad=0.4)
fig.savefig("figure1.png")

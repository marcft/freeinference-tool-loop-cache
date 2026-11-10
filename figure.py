"""Draws figure.png from around.csv, which numbers.py writes."""
import csv

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

INK, MUTED, GRID, SURFACE, BLUE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb", "#2a78d6"

rows = list(csv.DictReader(open("around.csv")))
x = [int(r["steps_from_the_losing_step"]) for r in rows]
median = [float(r["median_pct_of_prompt_cached"]) for r in rows]
low = [float(r["lower_quartile"]) for r in rows]
high = [float(r["upper_quartile"]) for r in rows]
steps = next(int(r["steps"]) for r in rows if r["steps_from_the_losing_step"] == "0")

fig, ax = plt.subplots(figsize=(7.4, 4.0), dpi=200, facecolor=SURFACE)
ax.set_facecolor(SURFACE)
ax.fill_between(x, low, high, color=BLUE, alpha=0.16, linewidth=0)
ax.plot(x, median, color=BLUE, linewidth=2, marker="o", markersize=8,
        markeredgecolor=SURFACE, markeredgewidth=2)

for i, offset in zip((-1, 0, 1), ((0, -16), (14, 2), (0, -16))):
    value = median[x.index(i)]
    ax.annotate(f"{value:g}%", (i, value), textcoords="offset points", xytext=offset,
                ha="center" if offset[0] == 0 else "left", va="center",
                fontsize=11, fontweight="bold", color=INK)

ax.set_xticks(x)
ax.set_xticklabels(["3 before", "2 before", "1 before", "the step", "1 after", "2 after", "3 after"])
ax.set_yticks([0, 25, 50, 75, 100])
ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
ax.set_ylim(-6, 108)
ax.set_xlim(-3.3, 3.3)
ax.tick_params(colors=MUTED, length=0, labelsize=10)
ax.grid(axis="y", color=GRID, linewidth=1)
ax.set_axisbelow(True)
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_color(GRID)
ax.set_xlabel("Steps of the same session, around the one that loses its cache", color=MUTED, fontsize=10, labelpad=8)

fig.text(0.02, 0.95, "The cache is gone for one step, then back", fontsize=14, fontweight="bold", color=INK, va="top")
fig.text(0.02, 0.875, f"Share of each prompt served from cache. Line: median over {steps:,} such steps. Band: middle half.",
         fontsize=10, color=MUTED, va="top")
fig.subplots_adjust(left=0.09, right=0.97, top=0.78, bottom=0.17)
fig.savefig("figure.png", facecolor=SURFACE)

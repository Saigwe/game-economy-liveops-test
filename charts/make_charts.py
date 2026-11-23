"""README charts from results/readout.md (written by `make all`).
Usage: python charts/make_charts.py [results/readout.md]"""
import re
import sys
from pathlib import Path

import style as st

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "readout.md"
OUT = ROOT / "docs" / "charts"


def tables(md: str) -> dict:
    """Markdown tables keyed by the nearest heading above them."""
    out, head, rows = {}, None, []
    for line in md.splitlines() + [""]:
        if line.startswith("#"):
            head = line.lstrip("# ").strip()
        elif line.startswith("|"):
            cells = [c.strip().strip("*") for c in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                rows.append(cells)
        elif rows:
            out[head] = [dict(zip(rows[0], r)) for r in rows[1:]]
            rows = []
    return out


def num(s: str) -> float:
    return float(re.sub(r"[^\d.\-]", "", s.replace("−", "-")))


t = tables(SRC.read_text(encoding="utf-8"))
res = next(v for k, v in t.items() if k.startswith("2."))
pts = [r for r in res if "pts" in r["Change"]]
pct = [r for r in res if "%" in r["Change"] and "pts" not in r["Change"] and r["Metric"] != "Sessions per player"]
f, (a1, a2) = st.plt.subplots(1, 2, figsize=(8, 3.3), dpi=150, gridspec_kw={"width_ratios": [1, 1.3]})
f.patch.set_facecolor(st.SURFACE)
for ax, rows, unit in ((a1, pts, "pts"), (a2, pct, "%")):
    ax.set_facecolor(st.SURFACE)
    for i, r in enumerate(rows):
        lo, hi = (num(x) for x in r["95% interval"].split(" to "))
        c = num(r["Change"])
        good = c > 0 if "Payer" not in r["Metric"] and "IAP" not in r["Metric"] else False
        col = st.S[2] if good else st.S[1]
        ax.plot([lo, hi], [i, i], color=col, lw=2.5, solid_capstyle="round")
        ax.scatter([c], [i], color=col, s=40, zorder=3)
        ax.annotate(f"{c:+.1f}{' pts' if unit == 'pts' else '%'}", (c, i), xytext=(0, 8), textcoords="offset points",
                    ha="center", fontsize=8.5, color=st.TEXT2)
    ax.axvline(0, color=st.TEXT2, lw=0.8)
    ax.margins(x=0.12)
    ax.set_yticks(range(len(rows)), [r["Metric"].replace(" (primary)", "\n(primary)").replace(" (guardrail)", "\n(guardrail)") for r in rows])
    ax.set_ylim(len(rows) - 0.5, -0.6)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    ax.xaxis.set_major_formatter(st.FuncFormatter(lambda v, _, u=unit: f"{v:+.0f}{' pts' if u == 'pts' else '%'}"))
a2.axvline(-5, color=st.CRITICAL, lw=1, ls="--")
a2.annotate("guardrail −5%", (-5, len(pct) - 0.5), xytext=(4, 2), textcoords="offset points", fontsize=8, color=st.CRITICAL)
st.head(a1, "Retention up, revenue past its guardrail", "Treatment minus control, 95% intervals", flush=True)
st.head(a2, "Decision: do not ship as is", "Relative changes, with the -5% revenue guardrail")
st.save(f, OUT / "readout_intervals.png")

eco = next(v for k, v in t.items() if k.startswith("3."))
f, ax = st.fig(8, 3.2)
for i, arm in enumerate(["control", "treatment"]):
    rows = [r for r in eco if r["Arm"] == arm]
    wk = [int(r["Week"]) for r in rows]
    ax.plot(wk, [num(r["Median balance"]) for r in rows], color=[st.MUTED, st.S[1]][i], lw=2, marker="o", ms=4,
            label=f"{arm.title()}: spends {rows[-1]['Spent / earned']} of what it earns")
    st.end_label(ax, wk[-1], num(rows[-1]["Median balance"]), rows[-1]["Median balance"])
ax.set_xticks(wk, [f"Week {w}" for w in wk])
ax.set_ylim(0, None)
ax.yaxis.set_major_formatter(st.FuncFormatter(lambda v, _: f"{v:,.0f}"))
c4 = num([r for r in eco if r["Arm"] == "control"][-1]["Median balance"])
t4 = num([r for r in eco if r["Arm"] == "treatment"][-1]["Median balance"])
st.head(ax, f"Coins pile up: the median treatment wallet is {t4 / c4 - 1:.0%} larger by week {wk[-1]}",
        "Median coin balance per player by week; more coins earned, a smaller share spent", legend=True, ncol=1)
st.save(f, OUT / "coin_balance.png")
print(f"wrote charts to {OUT}")

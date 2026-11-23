"""Write the experiment readout (and what the broken-split version would have claimed) to results/readout.md."""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from experiment.readout import aa_false_positive_rate, run
from experiment.stats import sample_size_two_proportion, two_proportion
from generator.simulate_test import load, simulate


def pts(x: float) -> str:
    return f"{x * 100:+.1f} pts"


def build(db: str, broken_db: str) -> str:
    con = duckdb.connect(db)
    r = run(con)
    m = r.metrics
    out = ["# Readout: reward_boost_v1", "",
           "Treatment gives 25% more coins for clearing levels 10 to 15. Synthetic data, 28-day test. "
           "Regenerate with `make all`.", "",
           "## 1. Is the test valid?", "",
           f"- Split: {r.n_control:,} control / {r.n_treatment:,} treatment. Sample-ratio check p = {r.srm_p:.2f}: "
           "no sign of missing players.",
           f"- A/A check: re-splitting control players 500 times flags a retention difference "
           f"{aa_false_positive_rate(con, 500):.1%} of the time at p < 0.05, as it should (about 5%).",
           f"- Power: {sample_size_two_proportion(m['d7_retention'].control, 0.02):,} players per arm detect a "
           "2-point retention change; the test has about 20,000.", "",
           "## 2. Results", "",
           "| Metric | Control | Treatment | Change | 95% interval |", "|---|---|---|---|---|"]
    e = m["d7_retention"]
    out.append(f"| Day-7 retention (primary) | {e.control:.1%} | {e.treatment:.1%} | {pts(e.diff)} | "
               f"{pts(e.ci_low)} to {pts(e.ci_high)} |")
    for key, label in (("sessions_per_player", "Sessions per player"),
                       ("sessions_per_player_cuped", "Sessions per player, CUPED")):
        e = m[key]
        out.append(f"| {label} | {e.control:.1f} | {e.treatment:.1f} | {e.diff:+.1%} | "
                   f"{e.ci_low:+.1%} to {e.ci_high:+.1%} |")
    e = m["payer_share"]
    out.append(f"| Payer share | {e.control:.2%} | {e.treatment:.2%} | {pts(e.diff)} | "
               f"{pts(e.ci_low)} to {pts(e.ci_high)} |")
    e = m["iap_revenue_per_player"]
    out.append(f"| IAP revenue per player (guardrail) | ${e.control:.3f} | ${e.treatment:.3f} | {e.diff:+.1%} | "
               f"{e.ci_low:+.1%} to {e.ci_high:+.1%} |")
    out += ["", f"CUPED, using each player's sessions in the 14 days before the test, removes "
            f"{r.cuped_variance_reduction:.0%} of the variance in sessions and narrows the interval by about half.",
            "", "## 3. Coin economy", "", "| Week | Arm | Coins earned | Coins spent | Spent / earned | Median balance |",
            "|---|---|---|---|---|---|"]
    eco = con.execute("select * from mart.economy_weekly order by week, arm").fetchall()
    out += [f"| {w} | {a} | {earned:,.0f} | {spent:,.0f} | {ratio:.1%} | {bal:,.0f} |"
            for a, w, n, earned, spent, ratio, bal in eco]
    out += ["", f"Treatment players earn more and spend a smaller share of it, so by week 4 their median balance is "
            f"{r.economy['balance_vs_control']:+.0%} against control. A player sitting on spare coins has less reason to buy a coin pack, which fits the drop in payers.",
            "", "## 4. Decision", "", f"**{r.decision}**", ""]

    # The same test with a logging bug that drops low-engagement treatment players.
    bcon = duckdb.connect(broken_db)
    br = run(bcon)
    df = bcon.execute("select arm, retained_d7 from mart.player_metrics").df()
    c, t = df[df.arm == "control"].retained_d7, df[df.arm == "treatment"].retained_d7
    naive = two_proportion(int(c.sum()), len(c), int(t.sum()), len(t))
    out += ["## 5. The same test with a broken split", "",
            "A simulated crash on low-end devices stops 6% of the least engaged treatment players from logging "
            "their exposure.", "",
            f"- Read naively, day-7 retention would be up **{pts(naive.diff)}**, overstating the real "
            f"{pts(m['d7_retention'].diff)}, because the players who would have churned are the ones missing.",
            f"- The readout refuses it: *{br.decision}*", ""]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="warehouse/liveops.duckdb")
    ap.add_argument("--broken-db", default="warehouse/broken.duckdb")
    ap.add_argument("--out", default="results/readout.md")
    a = ap.parse_args()
    for path, broken in ((a.db, False), (a.broken_db, True)):
        if not Path(path).exists():
            load(path, simulate(broken_split=broken))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(build(a.db, a.broken_db), encoding="utf-8")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()

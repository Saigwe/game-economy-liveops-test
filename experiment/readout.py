"""Experiment readout: validity checks first, then the primary metric, secondary metrics, guardrail and economy."""
from __future__ import annotations

from dataclasses import dataclass, field

import duckdb
import numpy as np

from .stats import Effect, cuped, non_inferior, relative_mean_diff, srm_check, two_proportion

SQL = """
create schema if not exists mart;

create or replace table mart.player_metrics as
select a.player_id, a.arm, p.pre_sessions, t.sessions, t.retained_d7, t.purchases, t.iap_usd
from raw.assignments a
join raw.player_pre_period p using (player_id)
join raw.player_test_period t using (player_id)
where a.experiment = 'reward_boost_v1';

-- Coin economy by arm and week. Every player appears every week (zero if they did not play), and the balance
-- starts at the 500 coins every player is given.
create or replace table mart.economy_weekly as
with grid as (
    select m.player_id, m.arm, w.week
    from mart.player_metrics m
    cross join (select unnest(range(1, 5)) as week) w
),
flows as (
    select player_id, week,
           sum(coins) filter (where flow = 'source') as earned,
           sum(coins) filter (where flow = 'sink') as spent
    from raw.economy_ledger
    group by all
),
balances as (
    select g.arm, g.player_id, g.week,
           coalesce(f.earned, 0) as earned, coalesce(f.spent, 0) as spent,
           500 + sum(coalesce(f.earned, 0) - coalesce(f.spent, 0))
                 over (partition by g.player_id order by g.week) as balance
    from grid g
    left join flows f using (player_id, week)
)
select arm, week, count(*) as players, sum(earned) as coins_earned, sum(spent) as coins_spent,
       round(sum(spent) / sum(earned), 4) as sink_to_source,
       median(balance) as median_balance
from balances
group by all
order by arm, week;
"""


@dataclass
class Readout:
    n_control: int
    n_treatment: int
    srm_p: float
    valid: bool
    metrics: dict[str, Effect] = field(default_factory=dict)
    cuped_variance_reduction: float | None = None
    guardrail_pass: bool | None = None
    economy: dict | None = None
    decision: str = ""


def run(con: duckdb.DuckDBPyConnection, guardrail_margin: float = 0.05, srm_alpha: float = 0.001,
        inflation_limit: float = 0.20) -> Readout:
    con.execute(SQL)
    df = con.execute("select * from mart.player_metrics").df()
    c, t = df[df.arm == "control"], df[df.arm == "treatment"]
    r = Readout(len(c), len(t), srm_check(len(c), len(t)), valid=True)
    if r.srm_p < srm_alpha:
        r.valid = False
        r.decision = (f"Invalid test: the split is {len(t) / len(df):.1%} treatment against a 50% design "
                      f"(SRM p = {r.srm_p:.1e}). Players are missing from one arm, so every metric is biased. "
                      "Find the cause before reading any result.")
        return r

    r.metrics["d7_retention"] = two_proportion(int(c.retained_d7.sum()), len(c), int(t.retained_d7.sum()), len(t))
    y = df.sessions.to_numpy(float)
    y_adj, _ = cuped(y, df.pre_sessions.to_numpy(float))
    is_t = (df.arm == "treatment").to_numpy()
    r.cuped_variance_reduction = float(1 - np.var(y_adj) / np.var(y))
    r.metrics["sessions_per_player"] = relative_mean_diff(y[~is_t], y[is_t])
    r.metrics["sessions_per_player_cuped"] = relative_mean_diff(y_adj[~is_t], y_adj[is_t])
    r.metrics["payer_share"] = two_proportion(int((c.purchases > 0).sum()), len(c),
                                              int((t.purchases > 0).sum()), len(t))
    r.metrics["iap_revenue_per_player"] = relative_mean_diff(c.iap_usd.to_numpy(float), t.iap_usd.to_numpy(float))
    r.guardrail_pass = non_inferior(r.metrics["iap_revenue_per_player"], guardrail_margin)

    eco = con.execute("select * from mart.economy_weekly").df()
    last = eco[eco.week == eco.week.max()].set_index("arm")
    growth = last.loc["treatment", "median_balance"] / last.loc["control", "median_balance"] - 1
    r.economy = {"balance_vs_control": float(growth),
                 "sink_to_source": {a: float(last.loc[a, "sink_to_source"]) for a in ("control", "treatment")},
                 "inflating": bool(growth > inflation_limit)}

    ret = r.metrics["d7_retention"]
    iap = r.metrics["iap_revenue_per_player"]
    win = ret.ci_low > 0
    if win and r.guardrail_pass and not r.economy["inflating"]:
        r.decision = "Ship: retention is up and neither revenue nor the economy is harmed."
    elif win:
        reasons = []
        if not r.guardrail_pass:
            reasons.append(f"IAP revenue per player is {iap.diff:+.1%} (could be as bad as {iap.ci_low:+.1%}, "
                           f"beyond the -{guardrail_margin:.0%} guardrail)")
        if r.economy["inflating"]:
            reasons.append(f"median coin balances are {growth:+.0%} against control")
        r.decision = (f"Do not ship as is. Day-7 retention is up {ret.diff * 100:+.1f} points "
                      f"({ret.ci_low * 100:+.1f} to {ret.ci_high * 100:+.1f}), but " + " and ".join(reasons) +
                      ". The reward is too generous: test a smaller boost, or the boost with a matching coin sink.")
    else:
        r.decision = "No ship: the primary metric did not improve."
    return r


def aa_false_positive_rate(con: duckdb.DuckDBPyConnection, sims: int = 200, seed: int = 1) -> float:
    """Re-split control players at random many times; the share of 'significant' retention results should be ~5%."""
    y = con.execute("select retained_d7 from mart.player_metrics where arm = 'control'").df().retained_d7.to_numpy()
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(sims):
        m = rng.random(len(y)) < 0.5
        e = two_proportion(int(y[~m].sum()), int((~m).sum()), int(y[m].sum()), int(m.sum()))
        hits += e.p_value < 0.05
    return hits / sims

"""Synthetic live-ops experiment in a free-to-play mobile game. Everything here is invented.

The test: `reward_boost_v1` gives treatment players 25% more coins for clearing levels 10 to 15, the hardest stretch
of the game. Assignment is a salted hash of the player id, 50/50.

Planted effects in treatment (what the readout must find):
- day-7 retention +2.5 points and sessions +6%: easier progress keeps players around;
- in-app purchase revenue per player -10%: with more free coins, fewer players buy coin packs;
- the coin economy inflates: players earn more and spend a smaller share of it, so balances pile up.

`broken_split=True` simulates a logging bug: treatment builds crash on some low-end devices before the exposure
event fires, so 6% of the least engaged treatment players silently drop out. The readout must refuse that data.

Usage: python generator/simulate_test.py --db warehouse/liveops.duckdb --players 40000 --seed 7 [--broken-split]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

EXPERIMENT = "reward_boost_v1"
START = datetime(2026, 3, 2)
WEEKS = 4
RETENTION_LIFT = 0.025
SESSION_LIFT = 0.06
IAP_PROB_CHANGE = -0.10
REWARD_BOOST = 0.25


def assign(player_ids: list[str]) -> np.ndarray:
    """Deterministic 50/50 split: salted MD5 of the player id. True = treatment."""
    return np.array([int(hashlib.md5(f"{EXPERIMENT}:{p}".encode()).hexdigest()[:8], 16) % 2 == 1
                     for p in player_ids])


def simulate(n: int = 40_000, seed: int = 7, broken_split: bool = False,
             effects: bool = True) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    pid = [f"u{i:07d}" for i in range(n)]
    t = assign(pid)
    k = 1.0 if effects else 0.0
    eng = rng.lognormal(0, 0.6, n)                                   # how much each player plays
    pre_sessions = rng.poisson(eng * 11)                             # 14 days before the test
    sessions = rng.poisson(eng * 22 * (1 + k * SESSION_LIFT * t))    # 28 days of the test
    p_ret = np.clip(0.30 * np.sqrt(eng), 0, 0.92) + k * RETENTION_LIFT * t
    retained = rng.random(n) < p_ret
    p_pay = np.clip(0.05 * eng ** 0.4, 0, 0.5) * (1 + k * IAP_PROB_CHANGE * t)
    payer = rng.random(n) < p_pay
    purchases = payer * (1 + rng.poisson(1.2 * eng ** 0.3))
    iap = np.round(purchases * rng.lognormal(np.log(8) - 0.25, 0.7, n), 2)

    players = pd.DataFrame({"player_id": pid, "arm": np.where(t, "treatment", "control"),
                            "pre_sessions": pre_sessions, "sessions": sessions, "retained_d7": retained,
                            "purchases": purchases, "iap_usd": iap})
    if broken_split:
        weakest = players[(players.arm == "treatment")].nsmallest(int(0.06 * (t.sum())), "pre_sessions").index
        players = players.drop(weakest)

    # Weekly coin ledger. Sources: level rewards, rewarded ads, coin packs. Sinks: upgrades, retries.
    rows = []
    week_share = rng.dirichlet(np.ones(WEEKS), len(players))
    tt = (players.arm == "treatment").to_numpy()
    s = players.sessions.to_numpy()
    for w in range(WEEKS):
        ws = s * week_share[:, w]
        level = ws * 110 * (1 + k * REWARD_BOOST * 0.6 * tt) * rng.lognormal(0, 0.15, len(players))
        ads = ws * 25 * rng.lognormal(0, 0.3, len(players))
        packs = players.purchases.to_numpy() * week_share[:, w] * 1200
        earned = level + ads + packs
        spend_share = np.clip(rng.normal(0.92 - k * 0.07 * tt, 0.05), 0.5, 1.0)  # treatment has less to buy
        upgrades = earned * spend_share * 0.75
        retries = earned * spend_share * 0.25
        for cat, flow, amt in (("level_rewards", "source", level), ("rewarded_ads", "source", ads),
                               ("coin_packs", "source", packs), ("upgrades", "sink", upgrades),
                               ("retries", "sink", retries)):
            rows.append(pd.DataFrame({"player_id": players.player_id.to_numpy(), "week": w + 1, "flow": flow,
                                      "category": cat, "coins": np.round(amt).astype(int)}))
    ledger = pd.concat(rows, ignore_index=True)
    ledger = ledger[ledger.coins > 0]

    assignments = players[["player_id", "arm"]].assign(
        experiment=EXPERIMENT,
        first_exposure_ts=[START + timedelta(seconds=int(x)) for x in rng.integers(0, 3 * 86_400, len(players))])
    return {
        "assignments": assignments[["experiment", "player_id", "arm", "first_exposure_ts"]],
        "player_pre_period": players[["player_id", "pre_sessions"]],
        "player_test_period": players[["player_id", "sessions", "retained_d7", "purchases", "iap_usd"]],
        "economy_ledger": ledger,
    }


def load(db_path: str | Path, tables: dict[str, pd.DataFrame]) -> dict[str, int]:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        con.execute("create schema if not exists raw")
        for name, df in tables.items():
            con.register("df", df)
            con.execute(f"create or replace table raw.{name} as select * from df")
            con.unregister("df")
        return {n: len(df) for n, df in tables.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="warehouse/liveops.duckdb")
    ap.add_argument("--players", type=int, default=40_000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--broken-split", action="store_true")
    a = ap.parse_args()
    print(json.dumps(load(a.db, simulate(a.players, a.seed, a.broken_split))))


if __name__ == "__main__":
    main()

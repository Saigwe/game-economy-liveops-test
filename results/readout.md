# Readout: reward_boost_v1

Treatment gives 25% more coins for clearing levels 10 to 15. Synthetic data, 28-day test. Regenerate with `make all`.

## 1. Is the test valid?

- Split: 19,933 control / 20,067 treatment. Sample-ratio check p = 0.50: no sign of missing players.
- A/A check: re-splitting control players 500 times flags a retention difference 6.4% of the time at p < 0.05, as it should (about 5%).
- Power: 8,564 players per arm detect a 2-point retention change; the test has about 20,000.

## 2. Results

| Metric | Control | Treatment | Change | 95% interval |
|---|---|---|---|---|
| Day-7 retention (primary) | 31.2% | 33.8% | +2.6 pts | +1.7 pts to +3.5 pts |
| Sessions per player | 26.2 | 27.7 | +5.9% | +4.5% to +7.3% |
| Sessions per player, CUPED | 26.1 | 27.7 | +6.1% | +5.4% to +6.7% |
| Payer share | 5.37% | 4.46% | -0.9 pts | -1.3 pts to -0.5 pts |
| IAP revenue per player (guardrail) | $0.991 | $0.798 | -19.5% | -29.5% to -9.5% |

CUPED, using each player's sessions in the 14 days before the test, removes 78% of the variance in sessions and narrows the interval by about half.

## 3. Coin economy

| Week | Arm | Coins earned | Coins spent | Spent / earned | Median balance |
|---|---|---|---|---|---|
| 1 | control | 18,587,198 | 17,083,937 | 91.9% | 538 |
| 1 | treatment | 21,873,248 | 18,588,166 | 85.0% | 595 |
| 2 | control | 18,652,624 | 17,144,950 | 91.9% | 600 |
| 2 | treatment | 22,175,265 | 18,834,674 | 84.9% | 739 |
| 3 | control | 18,926,627 | 17,400,499 | 91.9% | 668 |
| 3 | treatment | 21,926,437 | 18,632,171 | 85.0% | 887 |
| 4 | control | 18,387,664 | 16,898,745 | 91.9% | 734 |
| 4 | treatment | 21,944,795 | 18,647,715 | 85.0% | 1,033 |

Treatment players earn more and spend a smaller share of it, so by week 4 their median balance is +41% against control. A player sitting on spare coins has less reason to buy a coin pack, which fits the drop in payers.

## 4. Decision

**Do not ship as is. Day-7 retention is up +2.6 points (+1.7 to +3.5), but IAP revenue per player is -19.5% (could be as bad as -29.5%, beyond the -5% guardrail) and median coin balances are +41% against control. The reward is too generous: test a smaller boost, or the boost with a matching coin sink.**

## 5. The same test with a broken split

A simulated crash on low-end devices stops 6% of the least engaged treatment players from logging their exposure.

- Read naively, day-7 retention would be up **+3.3 pts**, overstating the real +2.6 pts, because the players who would have churned are the ones missing.
- The readout refuses it: *Invalid test: the split is 48.6% treatment against a 50% design (SRM p = 5.6e-08). Players are missing from one arm, so every metric is biased. Find the cause before reading any result.*

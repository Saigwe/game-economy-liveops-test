"""Known-answer tests for the statistics toolkit."""
import numpy as np
import pytest

from experiment.stats import (cuped, non_inferior, relative_mean_diff, sample_size_two_proportion, srm_check,
                              two_proportion)


def test_srm_passes_a_fair_split_and_catches_a_small_imbalance():
    assert srm_check(10_000, 10_050) > 0.5
    assert srm_check(10_000, 9_600) < 0.01


def test_two_proportion_matches_hand_calculation():
    e = two_proportion(300, 1000, 350, 1000)
    se = np.sqrt(0.3 * 0.7 / 1000 + 0.35 * 0.65 / 1000)
    assert e.diff == pytest.approx(0.05)
    assert e.ci_low == pytest.approx(0.05 - 1.959964 * se, rel=1e-5)
    assert e.p_value == pytest.approx(0.0178, abs=0.001)


def test_cuped_is_unbiased_and_cuts_variance_by_corr_squared():
    rng = np.random.default_rng(0)
    x = rng.normal(10, 3, 200_000)
    y = 2 + 0.8 * x + rng.normal(0, 2, x.size)
    adj, theta = cuped(y, x)
    rho2 = np.corrcoef(x, y)[0, 1] ** 2
    assert theta == pytest.approx(0.8, abs=0.01)
    assert adj.mean() == pytest.approx(y.mean())
    assert 1 - adj.var() / y.var() == pytest.approx(rho2, abs=0.005)


def test_relative_diff_interval_covers_a_known_lift():
    rng = np.random.default_rng(1)
    covered = 0
    for _ in range(300):
        c = rng.exponential(1.0, 4000)
        t = rng.exponential(1.1, 4000)
        e = relative_mean_diff(c, t)
        covered += e.ci_low <= 0.10 <= e.ci_high
    assert 0.92 <= covered / 300 <= 0.98


def test_guardrail_and_sample_size():
    rng = np.random.default_rng(2)
    flat = relative_mean_diff(rng.exponential(1, 50_000), rng.exponential(1, 50_000))
    worse = relative_mean_diff(rng.exponential(1, 50_000), rng.exponential(0.85, 50_000))
    assert non_inferior(flat, 0.05) and not non_inferior(worse, 0.05)
    assert sample_size_two_proportion(0.10, 0.01) == pytest.approx(14_750, rel=0.01)

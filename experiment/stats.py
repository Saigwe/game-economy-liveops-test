"""Small, tested statistics toolkit for experiment readouts."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

Z95 = stats.norm.ppf(0.975)


@dataclass
class Effect:
    control: float
    treatment: float
    diff: float              # treatment - control (absolute) or treatment / control - 1 (relative)
    ci_low: float
    ci_high: float
    p_value: float


def srm_check(n_control: int, n_treatment: int, expected_share: float = 0.5) -> float:
    """Sample-ratio mismatch: chi-square p-value that the split matches the design."""
    n = n_control + n_treatment
    return float(stats.chisquare([n_control, n_treatment],
                                 [n * (1 - expected_share), n * expected_share]).pvalue)


def two_proportion(x_c: int, n_c: int, x_t: int, n_t: int) -> Effect:
    """Absolute difference in conversion rates, Wald interval, pooled z-test p-value."""
    p_c, p_t = x_c / n_c, x_t / n_t
    se = np.sqrt(p_c * (1 - p_c) / n_c + p_t * (1 - p_t) / n_t)
    pool = (x_c + x_t) / (n_c + n_t)
    z = (p_t - p_c) / np.sqrt(pool * (1 - pool) * (1 / n_c + 1 / n_t))
    d = p_t - p_c
    return Effect(p_c, p_t, d, d - Z95 * se, d + Z95 * se, float(2 * stats.norm.sf(abs(z))))


def cuped(y: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, float]:
    """Adjust y with a pre-period covariate x. Returns (adjusted y, theta). Unbiased; variance falls by corr^2."""
    theta = np.cov(x, y)[0, 1] / np.var(x, ddof=1)
    return y - theta * (x - x.mean()), float(theta)


def relative_mean_diff(y_c: np.ndarray, y_t: np.ndarray) -> Effect:
    """treatment mean / control mean - 1, with a delta-method interval. Works for heavy-tailed revenue."""
    m_c, m_t = y_c.mean(), y_t.mean()
    v_c, v_t = y_c.var(ddof=1) / len(y_c), y_t.var(ddof=1) / len(y_t)
    rel = m_t / m_c - 1
    se = np.sqrt(v_t / m_c ** 2 + m_t ** 2 * v_c / m_c ** 4)
    return Effect(float(m_c), float(m_t), float(rel), float(rel - Z95 * se), float(rel + Z95 * se),
                  float(2 * stats.norm.sf(abs(rel / se))))


def non_inferior(effect: Effect, margin: float) -> bool:
    """Guardrail: the worst plausible change (interval low end) is no worse than -margin."""
    return effect.ci_low > -margin


def sample_size_two_proportion(p: float, lift: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Players per arm to detect an absolute lift in a rate p."""
    z_a, z_b = stats.norm.ppf(1 - alpha / 2), stats.norm.ppf(power)
    q = p + lift
    return int(np.ceil((z_a + z_b) ** 2 * (p * (1 - p) + q * (1 - q)) / lift ** 2))

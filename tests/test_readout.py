"""End to end: generated test -> SQL marts -> readout must recover the planted effects and reach the right call."""
import duckdb
import pytest

from experiment.readout import aa_false_positive_rate, run
from generator.simulate_test import IAP_PROB_CHANGE, RETENTION_LIFT, SESSION_LIFT, assign, load, simulate


@pytest.fixture(scope="module")
def readout(tmp_path_factory):
    db = tmp_path_factory.mktemp("wh") / "t.duckdb"
    load(db, simulate(40_000, seed=7))
    with duckdb.connect(str(db)) as con:
        yield run(con), aa_false_positive_rate(con, 200)


def test_assignment_is_deterministic_and_balanced():
    ids = [f"u{i:07d}" for i in range(20_000)]
    a = assign(ids)
    assert (a == assign(ids)).all()
    assert abs(a.mean() - 0.5) < 0.01


def test_valid_split_and_calibrated_aa(readout):
    r, aa = readout
    assert r.valid and r.srm_p > 0.01
    assert 0.02 <= aa <= 0.09


def test_planted_effects_are_inside_the_intervals(readout):
    r, _ = readout
    ret = r.metrics["d7_retention"]
    assert ret.ci_low <= RETENTION_LIFT <= ret.ci_high and ret.ci_low > 0
    ses = r.metrics["sessions_per_player_cuped"]
    assert ses.ci_low <= SESSION_LIFT <= ses.ci_high
    assert r.metrics["iap_revenue_per_player"].ci_high < 0
    assert r.metrics["payer_share"].diff / r.metrics["payer_share"].control == pytest.approx(IAP_PROB_CHANGE, abs=0.12)


def test_cuped_narrows_the_interval_without_moving_the_estimate(readout):
    r, _ = readout
    raw, adj = r.metrics["sessions_per_player"], r.metrics["sessions_per_player_cuped"]
    assert (adj.ci_high - adj.ci_low) < 0.6 * (raw.ci_high - raw.ci_low)
    assert adj.diff == pytest.approx(raw.diff, abs=0.01)
    assert r.cuped_variance_reduction > 0.5


def test_guardrail_fails_economy_inflates_and_decision_holds_back(readout):
    r, _ = readout
    assert r.guardrail_pass is False
    assert r.economy["inflating"]
    assert r.economy["sink_to_source"]["treatment"] < r.economy["sink_to_source"]["control"]
    assert r.decision.startswith("Do not ship as is")


def test_no_effects_means_no_ship(tmp_path):
    db = tmp_path / "flat.duckdb"
    load(db, simulate(20_000, seed=3, effects=False))
    with duckdb.connect(str(db)) as con:
        r = run(con)
    assert r.valid and r.decision.startswith("No ship")


def test_broken_split_is_refused(tmp_path):
    db = tmp_path / "broken.duckdb"
    load(db, simulate(40_000, seed=7, broken_split=True))
    with duckdb.connect(str(db)) as con:
        r = run(con)
    assert not r.valid and r.srm_p < 1e-6
    assert r.decision.startswith("Invalid test") and not r.metrics

from datetime import date

import numpy as np
import polars as pl
import pytest

from courtdelay.estimate import stock_flow, survival


def _ytd(court, subject, rows):
    return pl.DataFrame(
        [
            {
                "court": court,
                "period_start": f"{y}-01-01",
                "period_end": end,
                "subject_matter": subject,
                "commenced": c,
                "dispositions": d,
                "pending": p,
            }
            for (y, end, c, d, p) in rows
        ]
    )


def test_ytd_to_period_and_identity():
    # consistent stock-flow: pending grows by net flow each quarter
    df = _ytd(
        "FC",
        "TOTAL",
        [
            (2024, "2024-03-31", 100, 80, 1020),
            (2024, "2024-06-30", 210, 170, 1040),  # q2 flows: 110 / 90 -> +20
            (2024, "2024-09-30", 300, 280, 1020),  # q3: 90 / 110 -> -20
            (2024, "2024-12-31", 400, 360, 1040),  # q4: 100 / 80 -> +20
        ],
    )
    q = stock_flow.ytd_to_period(df)
    assert q["commenced_q"].to_list() == [100, 110, 90, 100]
    assert q["dispositions_q"].to_list() == [80, 90, 110, 80]
    assert q["q_start"].to_list() == ["2024-01-01", "2024-04-01", "2024-07-01", "2024-10-01"]
    chk = stock_flow.identity_check(q)
    assert chk.height == 3 and chk["ok"].all()
    w = stock_flow.littles_law(q)
    # q2: L = (1020+1040)/2 = 1030, 91 days, disposals 90/day*91 -> W = 1030 / (90/91) ≈ 1041 days
    row = w.filter(pl.col("period_end") == "2024-06-30").row(0, named=True)
    assert row["days"] == 91
    assert row["W_days_disposal_rate"] == pytest.approx(1030 / (90 / 91), rel=1e-6)
    assert row["backlog_ratio"] == pytest.approx(110 / 90)
    assert "steady-state" in row["bias_statement"]
    y = stock_flow.annual_rollup(w)
    assert y.height == 1 and y["commenced"][0] == 400 and y["dispositions"][0] == 360


def test_identity_violation_is_reported_not_hidden():
    df = _ytd(
        "FCA", "TOTAL", [(2024, "2024-03-31", 50, 40, 500), (2024, "2024-06-30", 100, 80, 700)]
    )
    chk = stock_flow.identity_check(stock_flow.ytd_to_period(df))
    assert chk.height == 1 and not chk["ok"][0] and chk["gap"][0] == 500 + 50 - 40 - 700


def test_km_no_censoring_matches_empirical_quantiles():
    d = np.array([10, 20, 30, 40, 50, 60, 70, 80, 90, 100], dtype=float)
    e = np.ones(10, dtype=bool)
    q = survival.km_quantiles(d, e, (0.5, 0.9))
    assert q[0.5] == 50 and q[0.9] == 90


def test_km_censoring_raises_quantiles_and_unreached_is_none():
    d = np.array([10, 20, 30, 40, 50, 60, 70, 80, 90, 100], dtype=float)
    e = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0], dtype=bool)  # last six still open
    q = survival.km_quantiles(d, e, (0.25, 0.5, 0.9))
    assert q[0.25] == 30  # S drops to 0.7 at t=30 (3/10 events)
    assert q[0.5] is None and q[0.9] is None  # curve never reaches 0.5
    ci = survival.bootstrap_quantiles(d, e, (0.25, 0.9), n_boot=50)
    assert ci[0.9] == (None, None)


def test_cohort_table():
    rng = np.random.default_rng(0)
    n = 200
    start = [date(2019, 1, 1) for _ in range(n)]
    durs = rng.exponential(200, n).astype(int)
    event = [date(2019, 1, 1).toordinal() + int(x) for x in durs]
    censor = date(2020, 1, 1)
    df = pl.DataFrame(
        {
            "cohort": [2019] * n,
            "filed": start,
            "ev": [date.fromordinal(x) if date.fromordinal(x) <= censor else None for x in event],
            "scraped": [censor] * n,
        }
    )
    t = survival.cohort_table(
        df, cohort_col="cohort", start_col="filed", event_col="ev", censor_col="scraped", n_boot=50
    )
    assert t.height == 1
    r = t.row(0, named=True)
    assert r["n"] == n and 0 < r["censored_share"] < 0.5
    assert 100 < r["p50_days"] < 220 and r["p50_lo"] <= r["p50_days"] <= r["p50_hi"]
    assert "Kaplan-Meier" in r["bias_statement"]


def test_competing_event_censors_at_its_own_date():
    # 40 files reach the event at 100 days; 60 are discontinued at 10 days (competing).
    df = pl.DataFrame(
        {
            "cohort": [1] * 100,
            "start": [date(2020, 1, 1)] * 100,
            "ev": [date(2020, 4, 10)] * 40 + [None] * 60,
            "comp": [date(2020, 4, 10)] * 40 + [date(2020, 1, 11)] * 60,
            "obs": [date(2022, 11, 1)] * 100,
        }
    )
    t = survival.cohort_table(
        df,
        cohort_col="cohort",
        start_col="start",
        event_col="ev",
        censor_col="obs",
        competing_col="comp",
        n_boot=20,
    )
    r = t.row(0, named=True)
    assert r["n_competing"] == 60
    # all remaining at-risk files have the event at day 100, so every quantile is 100
    assert r["p50_days"] == 100 and r["p90_days"] == 100


def test_cohort_table_suppresses_quantiles_in_censored_tail():
    from datetime import date, timedelta

    import polars as pl

    from courtdelay.estimate import survival

    start = date(2025, 1, 1)
    obs = date(2025, 12, 31)
    # 100 files: 30 close early, 69 are still open at the observation date, and one filed a
    # year earlier closes late, so the upper quantiles would be read off a single file
    rows = [{"c": "a", "start": start, "end": start + timedelta(days=10 + i)} for i in range(30)]
    rows += [{"c": "a", "start": start, "end": None} for _ in range(69)]
    rows += [{"c": "a", "start": date(2024, 1, 1), "end": date(2025, 12, 1)}]
    df = pl.DataFrame(rows).with_columns(pl.lit(obs).alias("obs"))
    kw = dict(cohort_col="c", start_col="start", event_col="end", censor_col="obs", n_boot=20)
    loose = survival.cohort_table(df, **kw)
    strict = survival.cohort_table(df, min_at_risk=20, **kw)
    assert loose["p50_days"][0] == 700.0
    assert strict["p50_days"][0] is None and strict["p50_lo"][0] is None
    # a fully observed small cohort keeps its quantiles
    full = pl.DataFrame(
        [{"c": "b", "start": start, "end": start + timedelta(days=i + 1)} for i in range(35)]
    ).with_columns(pl.lit(obs).alias("obs"))
    assert survival.cohort_table(full, min_at_risk=20, **kw)["p50_days"][0] is not None


def test_cumulative_incidence_sums_to_one_and_respects_competing():
    from courtdelay.estimate.survival import cumulative_incidence

    # 10 files: 4 heard (days 10..40), 4 end without a hearing (days 5..35), 2 still open at 100
    d = [10, 20, 30, 40, 5, 15, 25, 35, 100, 100]
    c = [1, 1, 1, 1, 2, 2, 2, 2, 0, 0]
    out = cumulative_incidence(d, c, (20, 50, 100))
    assert out[20] == (0.2, 0.2)
    heard, other = out[50]
    assert abs(heard - 0.4) < 1e-9 and abs(other - 0.4) < 1e-9  # 20% still open
    # censoring before any event leaves the estimate on the remaining files
    out = cumulative_incidence([1, 10, 20], [0, 1, 2], (30,))
    assert abs(out[30][0] - 0.5) < 1e-9 and abs(out[30][1] - 0.5) < 1e-9

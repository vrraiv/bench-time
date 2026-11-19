"""Kaplan–Meier duration estimates with right-censoring and bootstrap intervals (no extra deps).

Used for docket cohorts (S4 now; S10–S12 later): durations from filing to a stage event, with
files that have not reached the event censored at the observation (scrape) date.

``km_quantiles(durations, events, qs)`` returns the KM estimate of the requested quantiles
(median, p75, p90 …) or None when the survival curve never drops to that level (too much
censoring). ``bootstrap_quantiles`` resamples files with replacement and returns percentile CIs.
Every output carries n, n_events and the censoring share so the reader sees how much is inferred.
"""

from __future__ import annotations

import numpy as np
import polars as pl


def km_curve(durations: np.ndarray, events: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (times, survival) for the Kaplan–Meier estimator. ``events`` is 1 for observed,
    0 for censored. Times are the distinct event times in increasing order."""
    t = np.asarray(durations, dtype=float)
    e = np.asarray(events, dtype=bool)
    order = np.argsort(t, kind="stable")
    t, e = t[order], e[order]
    uniq = np.unique(t[e])
    n = len(t)
    surv = np.empty(len(uniq))
    s = 1.0
    at_risk_idx = 0
    for i, ti in enumerate(uniq):
        # number at risk: durations >= ti
        while at_risk_idx < n and t[at_risk_idx] < ti:
            at_risk_idx += 1
        at_risk = n - at_risk_idx
        d = np.sum((t == ti) & e)
        if at_risk > 0:
            s *= 1.0 - d / at_risk
        surv[i] = s
    return uniq, surv


def km_quantiles(durations, events, qs=(0.5, 0.75, 0.9)) -> dict[float, float | None]:
    """Quantile q is the smallest time at which S(t) <= 1 - q; None if never reached."""
    times, surv = km_curve(np.asarray(durations), np.asarray(events))
    out: dict[float, float | None] = {}
    for q in qs:
        idx = np.nonzero(surv <= 1.0 - q + 1e-9)[0]
        out[q] = float(times[idx[0]]) if len(idx) else None
    return out


def bootstrap_quantiles(
    durations, events, qs=(0.5, 0.75, 0.9), *, n_boot: int = 500, seed: int = 20261115, level=0.95
) -> dict[float, tuple[float | None, float | None]]:
    rng = np.random.default_rng(seed)
    d = np.asarray(durations, dtype=float)
    e = np.asarray(events, dtype=bool)
    n = len(d)
    draws: dict[float, list[float]] = {q: [] for q in qs}
    reached: dict[float, int] = dict.fromkeys(qs, 0)
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        qv = km_quantiles(d[idx], e[idx], qs)
        for q in qs:
            if qv[q] is not None:
                draws[q].append(qv[q])
                reached[q] += 1
    alpha = (1 - level) / 2
    out = {}
    for q in qs:
        if reached[q] < 0.9 * n_boot:  # quantile not identified in most resamples
            out[q] = (None, None)
        else:
            arr = np.asarray(draws[q])
            out[q] = (float(np.quantile(arr, alpha)), float(np.quantile(arr, 1 - alpha)))
    return out


def cohort_table(
    df: pl.DataFrame,
    *,
    cohort_col: str,
    start_col: str,
    event_col: str,
    censor_col: str,
    qs=(0.5, 0.75, 0.9),
    n_boot: int = 300,
    min_n: int = 30,
    label: str = "",
    competing_col: str | None = None,
    min_at_risk: int = 0,
    bias_statement: str = "Kaplan-Meier, right-censored at observation date; "
    "regex-classified events; immigration dockets only",
) -> pl.DataFrame:
    """KM quantiles per cohort. Rows with a null start are dropped; rows with a null event date are
    censored at ``competing_col`` when that is set and non-null (a competing terminal event, e.g.
    a discontinuance before any leave decision: cause-specific convention), else at
    ``censor_col`` (the observation date; must be non-null). ``n_competing`` is reported."""
    rows = []
    for cohort, sub in df.group_by(cohort_col, maintain_order=True):
        key = cohort[0] if isinstance(cohort, tuple) else cohort
        sub = sub.filter(pl.col(start_col).is_not_null() & pl.col(censor_col).is_not_null())
        if sub.height < min_n:
            continue
        ev = sub[event_col].is_not_null().to_numpy()
        censor_at = (
            pl.coalesce([pl.col(competing_col), pl.col(censor_col)])
            if competing_col
            else pl.col(censor_col)
        )
        n_comp = (
            sub.filter(pl.col(event_col).is_null() & pl.col(competing_col).is_not_null()).height
            if competing_col
            else 0
        )
        end = pl.when(pl.col(event_col).is_not_null()).then(pl.col(event_col)).otherwise(censor_at)
        dur = (
            sub.select((end - pl.col(start_col)).dt.total_days().alias("d"))["d"]
            .to_numpy()
            .astype(float)
        )
        keep = dur >= 0
        dur, ev = dur[keep], ev[keep]
        if len(dur) < min_n:
            continue
        qv = km_quantiles(dur, ev, qs)
        ci = bootstrap_quantiles(dur, ev, qs, n_boot=n_boot)
        row = {
            cohort_col: key,
            "n": int(len(dur)),
            "n_events": int(ev.sum()),
            "censored_share": float(1 - ev.mean()),
            "n_competing": int(n_comp),
            "estimand": label or f"{start_col} -> {event_col}",
            "bias_statement": bias_statement,
        }
        for q in qs:
            name = f"p{int(q * 100)}"
            row[f"{name}_days"] = qv[q]
            row[f"{name}_lo"], row[f"{name}_hi"] = ci[q]
            # a quantile read off a right tail thinned by censoring (few files still at risk,
            # and under half of the (1-q)*n a fully observed cohort would have) is unstable:
            # report it as not yet estimable
            at_risk = int((dur >= qv[q]).sum()) if qv[q] is not None else 0
            if qv[q] is not None and at_risk < min_at_risk and at_risk < 0.5 * (1 - q) * len(dur):
                row[f"{name}_days"] = row[f"{name}_lo"] = row[f"{name}_hi"] = None
        rows.append(row)
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def cumulative_incidence(durations, causes, times) -> dict[float, tuple[float, float]]:
    """Aalen-Johansen cumulative incidence with one competing risk.

    ``causes``: 0 = censored, 1 = the event of interest, 2 = the competing event (the file ended
    another way first). Returns {t: (P(event by t), P(competing event by t))}. Unlike 1 - KM with
    competing events censored, the two shares and the still-open share sum to one."""
    t = np.asarray(durations, dtype=float)
    c = np.asarray(causes, dtype=int)
    order = np.argsort(t, kind="stable")
    t, c = t[order], c[order]
    n = len(t)
    uniq = np.unique(t[c > 0])
    surv, f1, f2 = 1.0, 0.0, 0.0
    steps = []
    for ti in uniq:
        at_risk = n - np.searchsorted(t, ti, side="left")
        if at_risk <= 0:
            break
        here = t == ti
        d1, d2 = int(np.sum(here & (c == 1))), int(np.sum(here & (c == 2)))
        f1 += surv * d1 / at_risk
        f2 += surv * d2 / at_risk
        surv *= 1.0 - (d1 + d2) / at_risk
        steps.append((ti, f1, f2))
    out = {}
    for q in times:
        last = (0.0, 0.0)
        for ti, a, b in steps:
            if ti > q:
                break
            last = (a, b)
        out[q] = last
    return out


def cif_table(
    df: pl.DataFrame,
    *,
    cohort_col: str,
    start_col: str,
    event_col: str,
    competing_col: str,
    censor_col: str,
    times=(365, 730, 1095),
    n_boot: int = 200,
    min_n: int = 30,
    seed: int = 20261119,
    label: str = "",
    bias_statement: str = "",
) -> pl.DataFrame:
    """Cumulative incidence of ``event_col`` by cohort, with ``competing_col`` as the competing
    end and ``censor_col`` the observation date. A time point is reported only when the cohort
    has been observed that long (the latest start plus the time is before the observation date
    for at least half the cohort); bootstrap percentile intervals."""
    rows = []
    rng = np.random.default_rng(seed)
    for cohort, sub in df.group_by(cohort_col, maintain_order=True):
        key = cohort[0] if isinstance(cohort, tuple) else cohort
        sub = sub.filter(pl.col(start_col).is_not_null() & pl.col(censor_col).is_not_null())
        ev, comp = pl.col(event_col), pl.col(competing_col)
        first = pl.min_horizontal(ev, comp, pl.col(censor_col))
        x = sub.select(
            (first - pl.col(start_col)).dt.total_days().alias("d"),
            pl.when(ev.is_not_null() & (ev <= first))
            .then(1)
            .when(comp.is_not_null() & (comp <= first))
            .then(2)
            .otherwise(0)
            .alias("c"),
            (pl.col(censor_col) - pl.col(start_col)).dt.total_days().alias("follow"),
        ).filter(pl.col("d") >= 0)
        if x.height < min_n:
            continue
        d, c = x["d"].to_numpy().astype(float), x["c"].to_numpy()
        follow = x["follow"].to_numpy()
        est = cumulative_incidence(d, c, times)
        boots = {q: [] for q in times}
        for _ in range(n_boot):
            idx = rng.integers(0, len(d), len(d))
            b = cumulative_incidence(d[idx], c[idx], times)
            for q in times:
                boots[q].append(b[q][0])
        row = {
            cohort_col: key,
            "n": int(len(d)),
            "n_events": int((c == 1).sum()),
            "n_competing": int((c == 2).sum()),
            "open_share": float((c == 0).mean()),
            "estimand": label or f"{start_col} -> {event_col}",
            "bias_statement": bias_statement,
        }
        for q in times:
            name = f"by_{int(q)}d"
            seen = float((follow >= q).mean()) >= 0.5
            row[f"event_{name}"] = est[q][0] if seen else None
            row[f"event_{name}_lo"] = float(np.quantile(boots[q], 0.025)) if seen else None
            row[f"event_{name}_hi"] = float(np.quantile(boots[q], 0.975)) if seen else None
            row[f"competing_{name}"] = est[q][1] if seen else None
        rows.append(row)
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()

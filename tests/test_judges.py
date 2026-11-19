from datetime import date

import polars as pl

from courtdelay.estimate import judges


def test_judge_key_strips_titles_and_accents():
    assert judges.judge_key("The Honourable Mr. Justice Exemple") == "EXEMPLE"
    assert judges.judge_key("PRESENT: Madam Justice Élodie Témoin") == "TEMOIN"
    assert judges.judge_key("L'honorable juge de Fictif") == "DE FICTIF"
    assert judges.judge_key("EXEMPLE J.") == "EXEMPLE"
    assert judges.judge_key(None) is None and judges.judge_key("J.") is None


def test_court_year_table_has_no_names():
    rows = []
    for i in range(12):
        rows.append(("FC", date(2021, 1 + i, 3), "Mr. Justice Exemple", 20 + i))
        rows.append(("FC", date(2021, 1 + i, 4), "Madam Justice Témoin", 40))
    rows.append(("FC", date(2021, 5, 5), "Prothonotary Fictif", 5))
    rows.append(("FCA", date(2021, 5, 5), "EXEMPLE J.A.", 5))
    meta = pl.DataFrame(
        rows, schema=["court", "decision_date", "judges_line", "reserve_days"], orient="row"
    )
    dec = judges.judge_decisions(meta)
    assert set(dec["court"]) == {"FC"}  # appeal panels are out of scope
    comp = pl.DataFrame(
        {
            "court_code": ["FC"],
            "month": [date(2021, 6, 1)],
            "in_office": [4],
            "supernumerary": [0],
            "vacancies": [1],
        }
    )
    t = judges.court_year_table(dec, comp)
    r = t.row(0, named=True)
    assert r["n_judges_deciding"] == 2 and r["n_decisions"] == 24 and r["n_decisions_all"] == 25
    assert r["deciding_to_complement_ratio"] == 0.5 and r["n_judges_10plus"] == 2
    assert r["judge_reserve_p50_p50"] is None  # fewer than five judges: withheld
    assert "judge_key" not in t.columns
    blob = t.write_csv()
    assert "EXEMPLE" not in blob and "TEMOIN" not in blob and "Fictif" not in blob

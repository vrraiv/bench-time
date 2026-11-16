from courtdelay.common import paths
from courtdelay.sources import s9_fja_vacancies as s9

FIX = paths.fixtures_dir("s9") / "fja_2026-11-01.html"


def test_parse_as_of():
    assert s9.parse_as_of("NUMBER OF FEDERALLY APPOINTED JUDGES AS OF NOVEMBER 1, 2026") == (
        "2026-11-01"
    )
    assert s9.parse_as_of("Judges as of the 15 March 2011") == "2011-03-15"
    assert s9.parse_as_of("nothing here") is None


def test_parse_live_layout():
    snap = s9.parse_html(FIX.read_bytes(), capture_ts="20261115", url="fixture")
    assert snap.error is None and snap.as_of == "2026-11-01"
    rows = {(r["jurisdiction"], r["court"]): r for r in snap.rows}
    fc = rows[("Canada", "Federal Court")]
    assert fc == {
        "jurisdiction": "Canada",
        "court": "Federal Court",
        "in_office": 40,
        "supernumerary": 3,
        "grand_total": 43,
        "women": 21,
        "vacancies": 2,
    }
    scj = rows[("Ontario", "Superior Court of Justice")]
    assert scj["vacancies"] == 5 and scj["grand_total"] == 275
    assert s9.FEDERAL_COURTS <= {c for j, c in rows if j == "Canada"}
    assert s9.ONTARIO_COURTS <= {c for j, c in rows if j == "Ontario"}


def test_parse_handles_missing_tables():
    snap = s9.parse_html("<html><body><p>AS OF MAY 1, 2010</p></body></html>")
    assert snap.error == "no tables" and snap.as_of == "2010-05-01"

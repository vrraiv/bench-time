"""Synthetic decision headers modelled on real court formats; no real names or texts."""

from datetime import date

from courtdelay.sources import s3_a2aj_decisions as s3

FC_HEADER = """Federal Court
Cour fédérale
Date: 20230512
Docket: IMM-1234-22
Citation: 2023 FC 650
Ottawa, Ontario, May 12, 2023
PRESENT: The Honourable Madam Justice Example
BETWEEN:
A.B.
Applicant
and
THE MINISTER OF CITIZENSHIP AND IMMIGRATION
Respondent
JUDGMENT AND REASONS
Heard at Toronto, Ontario, on April 3, 2023.
"""

FCA_HEADER_FR = """Cour d'appel fédérale
Date : 20220218
Dossier : A-123-21
Référence : 2022 CAF 30
CORAM : LE JUGE EXEMPLE
LA JUGE MODÈLE
ENTRE :
X.Y.
appelant
et
SA MAJESTÉ LE ROI
intimé
Audience tenue à Montréal (Québec), les 7 et 8 décembre 2021.
Jugement rendu à Ottawa (Ontario), le 18 février 2022.
"""

TCC_HEADER = """Docket: 2019-1234(IT)G
BETWEEN:
C.D.,
Appellant,
and
HIS MAJESTY THE KING,
Respondent.
Appeal heard on January 15 and 16, 2024, at Toronto, Ontario
Before: The Honourable Justice Sample
JUDGMENT
Signed at Ottawa, Canada, this 2nd day of May 2024.
"""

ONCA_HEADER = """COURT OF APPEAL FOR ONTARIO
CITATION: R. v. E.F., 2024 ONCA 100
DATE: 20240209
DOCKET: C70001
Doherty, Example and Sample JJ.A.
BETWEEN
His Majesty the King
Respondent
and
E.F.
Appellant
Heard: November 20, 2023
On appeal from the conviction entered by Justice G.H. of the Superior Court of Justice,
dated March 3, 2022.
"""

SCC_HEADER = """SUPREME COURT OF CANADA
Citation: R. v. I.J., 2021 SCC 10
Appeal Heard: October 7, 2020
Judgment Rendered: March 26, 2021
Docket: 38888
Between:
I.J.
Appellant
and
His Majesty The King
Respondent
Coram: Wagner C.J. and Abella, Moldaver, Karakatsanis, Côté, Brown, Rowe, Martin and Kasirer JJ.
"""


def test_fc_english_header():
    p = s3.parse_header(FC_HEADER, "FC")
    assert p["hearing_date"] == date(2023, 4, 3) and p["hearing_dates_n"] == 1
    assert p["file_numbers"] == "IMM-1234-22"
    assert "Justice Example" in p["judges_line"]


def test_fca_french_header_two_day_hearing():
    p = s3.parse_header(FCA_HEADER_FR, "FCA")
    assert p["hearing_date"] == date(2021, 12, 7)
    assert p["hearing_last_date"] == date(2021, 12, 8) and p["hearing_dates_n"] == 2
    assert p["file_numbers"] == "A-123-21"
    assert p["judgment_date_text"] == date(2022, 2, 18)


def test_tcc_header_procedure_and_multi_day():
    p = s3.parse_header(TCC_HEADER, "TCC")
    assert p["hearing_date"] == date(2024, 1, 15) and p["hearing_last_date"] == date(2024, 1, 16)
    assert p["file_numbers"] == "2019-1234(IT)G" and p["tcc_procedure"] == "general"
    assert (
        s3.parse_header(TCC_HEADER.replace("(IT)G", "(IT)I"), "TCC")["tcc_procedure"] == "informal"
    )


def test_onca_header_lower_court_date():
    p = s3.parse_header(ONCA_HEADER, "ONCA")
    assert p["hearing_date"] == date(2023, 11, 20)
    assert p["file_numbers"] == "C70001"
    assert p["lower_court_date"] == date(2022, 3, 3)


def test_scc_header():
    p = s3.parse_header(SCC_HEADER, "SCC")
    assert p["hearing_date"] == date(2020, 10, 7)
    assert p["file_numbers"] == "38888"
    assert p["judges_line"].startswith("Wagner C.J.")


def test_empty_and_dateless():
    p = s3.parse_header(None, "FC")
    assert p["hearing_date"] is None and p["file_numbers"] is None
    p = s3.parse_header("No useful header here.", "ONCA")
    assert p["hearing_date"] is None


FC_TAIL = """JUDGMENT in IMM-1234-22
THIS COURT'S JUDGMENT is that the application is dismissed.
"Jane Example"
Judge
FEDERAL COURT
SOLICITORS OF RECORD
DOCKET: IMM-1234-22
STYLE OF CAUSE: A.B. v THE MINISTER OF CITIZENSHIP AND IMMIGRATION
PLACE OF HEARING: TORONTO, ONTARIO
DATE OF HEARING: APRIL 3, 2023
JUDGMENT AND REASONS: EXAMPLE J.
DATED: MAY 12, 2023
"""

FCA_WRITTEN = """Federal Court of Appeal
Date: 20240322
Docket: A-16-23
Citation: 2024 FCA 61
CORAM: WEBB J.A. RENNIE J.A. BIRINGER J.A.
BETWEEN:
HIS MAJESTY THE KING
Appellant
and
C.D.
Respondent
Dealt with in writing without appearance of parties.
Order delivered at Ottawa, Ontario, on March 22, 2024.
"""


def test_fc_hearing_date_in_tail_block():
    head = FC_HEADER.replace("Heard at Toronto, Ontario, on April 3, 2023.\n", "")
    p = s3.parse_header(head, "FC", tail=FC_TAIL)
    assert p["hearing_date"] == date(2023, 4, 3) and p["hearing_mode"] == "oral"


def test_fca_written_disposition():
    p = s3.parse_header(FCA_WRITTEN, "FCA", tail="")
    assert p["hearing_date"] is None and p["hearing_mode"] == "written"
    assert p["judges_line"].startswith("WEBB J.A.")
    assert p["file_numbers"] == "A-16-23"


def test_judges_line_never_captures_party_block():
    text = "Before the court were the applicant and respondent.\nBETWEEN:\nX\nApplicant\n"
    p = s3.parse_header(text, "FC", tail="")
    assert p["judges_line"] is None or "applicant" not in p["judges_line"].lower()


def test_tcc_file_numbers_without_procedure_letter():
    for nbr in ("2019-1234(EI)", "2019-88(CPP)", "2020-45(GST)APP", "2021-7(IT)APP", "98-123(IT)G"):
        p = s3.parse_header(TCC_HEADER.replace("2019-1234(IT)G", nbr), "TCC")
        assert p["file_numbers"] == nbr, nbr
    # the letter that starts the next word is not taken for a procedure suffix
    p = s3.parse_header(TCC_HEADER.replace("2019-1234(IT)G", "2019-1234(EI) IN"), "TCC")
    assert p["file_numbers"] == "2019-1234(EI)"

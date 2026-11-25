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


FC_PAGE = """
[12] The application is dismissed.
FEDERAL COURT
SOLICITORS OF RECORD
DOCKET:
IMM-1234-23
STYLE OF CAUSE:
PERSON ONE v. THE MINISTER OF CITIZENSHIP AND IMMIGRATION
PLACE OF HEARING:
by videoconference
DATE OF HEARING:
April 16, 2024
JUDGMENT and reasons:
JUDGE ONE J.
DATED:
April 25, 2024
APPEARANCES:
LAWYER ONE
For The Applicant
SOLICITORS OF RECORD:
FIRM ONE LLP
"""

FCA_BENCH_PAGE = """
FEDERAL COURT OF APPEAL
NAMES OF COUNSEL AND SOLICITORS OF RECORD
DOCKET:
A-12-24
STYLE OF CAUSE:
PERSON TWO v. ATTORNEY GENERAL OF CANADA
PLACE OF HEARING:
Ottawa, Ontario
DATE OF HEARING:
October 1, 2024
REASONS FOR JUDGMENT OF THE COURT BY:
JUDGE TWO J.A.
DELIVERED FROM THE BENCH BY:
JUDGE TWO J.A.
APPEARANCES:
LAWYER TWO
"""

TCC_PAGE = """
CITATION:
2024 TCC 70
COURT FILE NO.:
2020-515(GST)G
STYLE OF CAUSE:
PERSON THREE v. HIS MAJESTY THE KING
PLACE OF HEARING:
Toronto, Ontario
DATE OF HEARING:
April 9 and 10, 2024
REASONS FOR JUDGMENT BY:
The Honourable Justice Judge Three
DATE OF JUDGMENT:
May 15, 2024
APPEARANCES:
LAWYER THREE
COUNSEL OF RECORD:
Name:
LAWYER THREE
[1] A footnote after the page.
"""

FR_PAGE = """
AVOCATS INSCRITS AU DOSSIER
DOSSIER :
IMM-10960-22
INTITULÉ :
PERSON FOUR c LE MINISTRE
LIEU DE L’AUDIENCE :
Toronto (Ontario)
DATE DE L’AUDIENCE :
Le 30 novembre 2023
ORDONNANCE ET MOTIFS :
JUDGE FOUR
DATE DE L’ORDONNANCE ET DES MOTIFS :
Le 12 décembre 2023
COMPARUTIONS :
LAWYER FOUR
"""


def test_closing_page_fields():
    p = s3.page_fields(FC_PAGE)
    assert p["page_found"] and p["page_place_kind"] == "video"
    assert p["page_hearing_last_date"] == date(2024, 4, 16)
    assert p["page_decision_kind"] == "judgment" and p["page_from_bench"] is False
    assert p["page_dated"] == date(2024, 4, 25) and p["page_judges"] == "JUDGE ONE J."
    q = s3.page_fields(FCA_BENCH_PAGE)
    assert q["page_place_kind"] == "in person" and q["page_dated"] is None
    assert q["page_decision_kind"] == "judgment" and q["page_from_bench"] is True
    t = s3.page_fields(TCC_PAGE)
    assert t["page_hearing_last_date"] == date(2024, 4, 10)
    assert t["page_dated"] == date(2024, 5, 15) and t["page_decision_kind"] == "judgment"
    f = s3.page_fields(FR_PAGE)
    assert f["page_decision_kind"] == "order" and f["page_dated"] == date(2023, 12, 12)
    assert f["page_hearing_last_date"] == date(2023, 11, 30)
    assert s3.page_fields("no page here")["page_found"] is False


def test_closing_page_never_keeps_names():
    for text in (FC_PAGE, FCA_BENCH_PAGE, TCC_PAGE, FR_PAGE):
        p = s3.page_fields(text)
        blob = repr({k: v for k, v in p.items() if k != "page_judges"})
        assert "PERSON" not in blob and "LAWYER" not in blob and "FIRM" not in blob


def test_counsel_counts_without_names():
    fc = """STYLE OF CAUSE:
PERSON ONE v. MINISTER
APPEARANCES:
LAWYER ONE
For The Applicant
LAWYER TWO
LAWYER THREE
For The Respondent
SOLICITORS OF RECORD:
FIRM ONE
"""
    c = s3.counsel_counts(fc)
    assert c == {
        "n_counsel": 3,
        "n_counsel_first": 1,
        "n_counsel_other": 2,
        "n_counsel_intervener": 0,
        "self_represented": False,
    }
    self_rep = """APPEARANCES:
PERSON TWO
ON HER OWN BEHALF
LAWYER FOUR
For The Respondent
SOLICITORS OF RECORD:
"""
    c = s3.counsel_counts(self_rep)
    assert c["self_represented"] and c["n_counsel_first"] == 0 and c["n_counsel_other"] == 1
    tcc = """APPEARANCES:
Counsel for the Appellant:
LAWYER FIVE
LAWYER SIX
Counsel for the Respondent:
LAWYER SEVEN
COUNSEL OF RECORD:
"""
    c = s3.counsel_counts(tcc)
    assert (c["n_counsel_first"], c["n_counsel_other"], c["n_counsel"]) == (2, 1, 3)
    tcc_self = """APPEARANCES:
For the Appellant:
The Appellant himself
Counsel for the Respondent:
LAWYER EIGHT
COUNSEL OF RECORD:
"""
    c = s3.counsel_counts(tcc_self)
    assert c["self_represented"] and c["n_counsel"] == 1
    assert "LAWYER" not in repr(c)


def test_place_city():
    assert s3._place_city("MontrEal, QuEbec") == "Montréal"
    assert s3._place_city("Toronto, Ontario") == "Toronto"
    assert s3._place_city("Québec (Québec)") == "Québec"
    assert s3._place_city("by videoconference") is None
    assert s3._place_city("Ottawa, Ontario (by videoconference)") is None
    assert s3._place_city("Held at Toronto, Ontario") == "Toronto"
    assert s3._place_city("St. John’s, Newfoundland and Labrador") == "St. John's"

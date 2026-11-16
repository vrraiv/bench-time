"""Page text copied from the ONCA 2023-2024 annual report appendix (aggregate statistics only)."""

from courtdelay.sources import s6_onca_annual_report as s6

PAGE_91 = """Phase #3: Hearing Date to Decision Release
Year Civil Criminal Inmate Average Total
(Excluding Inmate) Days
2023 60.24 57.40 28.13 55.94
2024 65.03 62.53 23.95 59.28
87 2023-2024 Report
"""
CHART_PAGE_71 = """Phase #1: Filing to Scheduling Readiness
Appeals are considered filed when a party files a notice of appeal.
2014 2015 2016 2017 2018 2019 2020 2021 2022 2023 2024
"""
PAGE_85 = """Outcomes of Appeals Heard on Their Merits
Civil Appeals Allowed or Dismissed on Their Merits
2024 94 321 22.7% 77.3%
"""


def test_parse_timeline_table():
    rows = s6.parse_page(PAGE_91, 91)
    civil = {r["year"]: r["value"] for r in rows if r["column"] == "civil"}
    assert civil == {2023: 60.24, 2024: 65.03}
    assert {r["table"] for r in rows} == {"timeline_hearing_to_decision"}


def test_chart_page_and_outcome_percentages_are_not_misread():
    assert s6.parse_page(CHART_PAGE_71, 71) == []
    assert s6.parse_page(PAGE_85, 85) == []  # 4 values do not fit the 3-column merits table

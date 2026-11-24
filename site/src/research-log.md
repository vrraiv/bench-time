---
title: Research log
---

# Research log

Changes that matter for the research: what data we hold, how files and events are defined, what the results are, decisions taken, and open questions. Code housekeeping is left out; the full history is in the repository. Newest first.

Held-back results (Tax Court, appeal chains, Supreme Court, pending-file counts, judges) are described here but their figures are not quoted; they are on the [results under review](./review) page.

**Kinds of entry:** _Data_ (coverage and collection) · _Definitions_ (how a file, event or count is defined) · _Results_ · _Decision_ (by the project lead) · _Open_ (questions not yet settled).

## 2026-11-23

- _Decision_: Questions the practitioner could not answer are kept on a new "open issues" page until they are settled or disclosed next to the results they affect, with the disclosure wording drafted now. It starts with three: what a sealed-envelope entry means, how confidentiality and protective orders differ, and which Tax Court entry records the court itself adjourning a hearing. Whether to put questions to the Federal Court and Tax Court registries, and who would ask, is now a decision on the questions page, as is raising the confidentiality questions with an outside lawyer who has researched Federal Court timing.
- _Open_: The practitioner answered the first round of questions (all 39, on the federal courts' statistics, confidentiality markers, Supreme Court leave applications and Tax Court entries). The questions and answers are kept on a new "earlier rounds" page linked from the questions page. Fourteen follow-ups replace them; most ask her to look at a file we name. Several points she suggested putting to the Federal Court Registry or the Court; whether and how to do that is for the project lead.
- _Open_: What the answers point to (none of it applied to the tables yet, and several answers were given as her provisional view). When files are consolidated, an ending in the lead file ends them all; files that are only managed together may not follow it (a follow-up asks how to tell them apart). An order in a lead file ending a list of files applies to each, as we already assumed. In the Tax Court, minutes of hearing are kept for motions, status hearings and conference calls as well as trials, so that entry alone does not mark the trial; files bound by a lead case are not paused; the joint application for a hearing is the right marker that the parties are ready; abeyance is at a party's request. For the Supreme Court, judgments given at the hearing should be reported apart from reserved judgments, and the wait for leave should be shown from both starting dates. Her provisional view is that files carrying confidentiality or publication-ban entries need not be left out of counts; that waits for the follow-ups.
- _Data_: Found while preparing the follow-ups: for Tax Court files that began as an extension-of-time application, the court's listed filing date is usually within a week of the day the application became an appeal, typically about five months after the file's first entry. Our Tax Court waits for those files therefore start at the conversion. How the clock should start is a follow-up question. It also appears that an appeal keeps the application's number, so the application files we hold are mostly ones that never became appeals (also a follow-up).
- _Open_: Our rule for leaving out the Crown's tax-collection files from the Federal Court tables also catches some ordinary tax and customs appeals brought by way of action. The practitioner is asked to confirm; if so, the rule will be narrowed, which would change the Federal Court cohort tables slightly.

- _Data_: The Ontario Court of Justice updated its 2026 criminal statistics workbooks in place; our tables now run to September 2026 (six more months; the rolling 12-month offence table moves to October 2025 to September 2026). Months the 2026 workbook no longer covers are taken from the 2025 workbook, with the same values.
- _Data_: Statistics Canada's site was down or intermittent from 21 to 23 November (announced maintenance that overran). Nothing wrong was saved or published. Statistics Canada tables are now downloaded directly as one file per table, and a "site unavailable" page is recognized, retried and never kept.
- _Decision_: Weekly updates now propose changes to published tables as pull requests (open-data tables weekly; every table, with the court files re-read, on the first Sunday of each month), each approved by the project lead before it goes in. The GitHub schedules for Statistics Canada and the courts' statistics pages become manual fallbacks.
- _Decision_: A research log (this page) and a status summary for research partners, linked from the questions page, are kept up to date.

## 2026-11-22

- _Definitions_: Where one of our tables mirrors a table a court publishes, it follows the court's definition as closely as the files allow and states the definition next to the table, including what it leaves out. Counts are never scaled to a court's totals.
- _Definitions_: A Federal Court or Federal Court of Appeal file also ends when an order in a lead file ends it (one order closing many related files), when a discontinuance is copied from a related file, or, from 2026, on a final judgment entry without the old marker.
- _Definitions_: Federal Court tables leave out the Crown's tax-collection files (certificates registered for enforcement), which the Court appears not to count as proceedings. The Federal Court of Appeal comparison sets aside the Court's "preliminary applications", which are not appeal files.
- _Results_: Federal Court of Appeal endings now match the Court's published figures at 94 to 100 percent a year. An earlier figure of 85 to 92 percent was wrong: it compared against a total that includes preliminary applications.
- _Data_: A sample of 660 Federal Court immigration files from before 2022, to test whether older files explain the shortfall in late-2025 immigration endings. They do not.
- _Open_: Federal Court judicial-review endings remain 2 to 3 percent short of the Court's count in 2024 to 2026; immigration endings are short in the last quarter of 2025; about 110 dormant appeal files have no ending on the record. Which file types the courts leave out of their counts is not published; seven questions on this went to the questions page.
- _Decision_: Questions for the practitioner are on a "Questions for review" page on the preview site, with replies stored there.

## 2026-11-21

- _Definitions_: From 1 January 2026 the federal courts' registry writes entries in a new format ("Order (Final) dated …", "Result - Leave dismissed"). The end-of-file rules now read both formats; the shortfall in 2026 endings came from the new format not being recognized.
- _Results_: The Federal Court's published counts of pending files are shown as the Court's own figures, with quarters where the court was not in a steady state flagged, and compared with counts built from the court files (held back).

## 2026-11-20

- _Data_: Supreme Court of Canada: every case page from 2010 collected (9,131 files): leave and appeal stage dates and the court appealed from.
- _Results_: Supreme Court leave and appeal stages built by court of origin (held back). Leave decisions take longer for cases from Quebec. Our figures reproduce the Court's published averages.
- _Decision_: Supreme Court files with sealing or publication-ban notes (about 7 percent) are kept and counted on the private preview only, until the practitioner's guidance settles the rule.
- _Data_: Statistics Canada tables refreshed monthly and the courts' statistics pages quarterly, with changes proposed as pull requests. A build never replaces a published table with older source data.

## 2026-11-19

- _Data_: Collection complete: every Federal Court of Appeal file and every Federal Court general file from recent years, Federal Court immigration samples (1,000 files a year for 2023 to 2026, plus a 300-file 2022 sample overlapping the Refugee Law Lab collection), and every recent Tax Court file.
- _Definitions_: A Federal Court or Federal Court of Appeal file ends at the court's "Final Decision" marker, or at a discontinuance; a mention of a judgment alone no longer ends a file. Registered tribunal decisions and certificates are flagged and kept out of duration tables. Hearing minutes in French and at the appeal court count as hearings; case conferences do not.
- _Results_: Published decisions linked to their docket files by court file number (Federal Court, Federal Court of Appeal, immigration, Tax Court). Federal Court and Federal Court of Appeal cohort tables, following each year's new files forward. Federal Court and Federal Court of Appeal filings match the courts' statistics within 2.5 percent. Tax Court hearing wait, appeal chains, and judges against the judicial complement built (held back).
- _Decision_: Files carrying a confidentiality marker are kept and the markers counted, not dropped, for the Federal Court, Federal Court of Appeal and the Refugee Law Lab collection, pending the practitioner's reading of what the markers mean.
- _Decision_: Federal Court and Federal Court of Appeal cohort tables and link match rates are published; Tax Court tables, appeal chains, pending-file counts and the judges table are held back.
- _Data_: The Ontario Superior Court scheduling service's terms bar automated collection; it is not collected. Statistics Canada's civil timing tables by level of court added as the available view of the Superior Court.

## 2026-11-18

- _Decision_: No individual names in published results, judges included. Judge names may be used only to link records; figures about judges appear only as anonymous distributions.
- _Definitions_: Tax Court: a file ends when the court's status field says so, or on a dismissal, allowance, quashing or withdrawal entry; files held in abeyance and released are tracked. Provisional Tax Court cohort tables built (held back).
- _Decision_: Cross-source linkages planned: decisions to docket files, hearing-date repair, appeal chains, judges against complement.

## 2026-11-16

- _Data_: Federal Court, Federal Court of Appeal and Tax Court docket collection built (one public record per file, party names dropped as each file is read), run single-threaded at the approved pace.
- _Data_: Court of Appeal for Ontario annual report tables (2014 to 2024) and Supreme Court time lapses from 2002 added.
- _Decision_: Derived summary tables are committed with an attribution table. A2AJ material is read as allowing no commercial use and no full-text reproduction.

## 2026-11-15

- _Data_: First sources verified and collected: Statistics Canada criminal and civil court tables, Supreme Court annual statistics, federal court workload tables, Ontario Court of Justice criminal statistics, judicial vacancy lists, and the A2AJ decisions collection (dates only).
- _Definitions_: Delay measured descriptively: durations of completed and open files (survival curves, so open files are not ignored), and stock-and-flow checks against the courts' published counts.

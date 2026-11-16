# Derived tables

Aggregate tables produced by `uv run courtdelay build` from the sources below. They contain no
party names, no decision texts and no per-file docket records. Each table carries a
`bias_statement` column; definitions are in `docs/methods.md`, vintages in `data/manifest.jsonl`.

| Prefix | Source | Licence / terms | Attribution |
|---|---|---|---|
| s1_ | Statistics Canada, Integrated Criminal Court Survey | Statistics Canada Open Licence | "Source: Statistics Canada, tables 35-10-0027/0029/0172-0176. Reproduced and distributed on an 'as is' basis with the permission of Statistics Canada." |
| s3_ | A2AJ Canadian Case Law (Hugging Face) | A2AJ work MIT; upstream court terms (non-commercial, no full-text reproduction) | Rehaag, Wallace & McCarten, "A2AJ Canadian Case Law" (2025), Hugging Face |
| s4_ | Refugee Law Lab, Luck of the Draw III | CC BY-NC 4.0 | Refugee Law Lab, York University |
| s5_ | Supreme Court of Canada statistics | Government of Canada non-commercial reproduction | Supreme Court of Canada |
| s6_ | Court of Appeal for Ontario Annual Report 2023-2024 | Ontario Courts publication | Court of Appeal for Ontario |
| s7_ | Ontario Court of Justice criminal statistics | Ministry of the Attorney General data; the Court disclaims accuracy | Ontario Court of Justice |
| s8_ | Federal Court, Federal Court of Appeal activity summaries | Government of Canada non-commercial reproduction | Federal Court; Federal Court of Appeal |
| s9_ | Commissioner for Federal Judicial Affairs, via the Internet Archive | Government of Canada non-commercial reproduction | Office of the Commissioner for Federal Judicial Affairs Canada |

Use is non-commercial (inherited from the CC BY-NC and court terms above).

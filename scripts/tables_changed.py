"""List the published tables whose data changed, ignoring the fetch timestamp.

Used by the monthly Statistics Canada workflow. A rebuilt table always carries a new
``fetched_at`` value, so a plain ``git diff`` would report a change every month. This compares
each modified CSV in ``site/src/data`` with the committed copy after dropping that column, puts
back the committed copy when nothing else differs, and prints the paths that really changed
(one per line; nothing when there is no change).
"""

from __future__ import annotations

import csv
import io
import subprocess
import sys

DATA = "site/src/data"
IGNORED = {"fetched_at"}


def rows(text: str) -> list[dict]:
    return [
        {k: v for k, v in r.items() if k not in IGNORED} for r in csv.DictReader(io.StringIO(text))
    ]


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def main() -> int:
    changed = []
    for line in git("status", "--porcelain", "--", DATA).splitlines():
        state, path = line[:2], line[3:].strip().strip('"')
        if not path.endswith(".csv"):
            continue
        if "?" in state or "A" in state:  # a table that did not exist before
            changed.append(path)
            continue
        with open(path, encoding="utf-8", newline="") as fh:
            new = fh.read()
        if rows(git("show", f"HEAD:{path}")) == rows(new):
            git("checkout", "--", path)
        else:
            changed.append(path)
    if changed:  # print nothing at all when there is no change, so the output file stays empty
        print("\n".join(changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Command-line entry point: ``courtdelay fetch <source>``, ``courtdelay build``.

Sources are modules under ``courtdelay.sources`` named ``<id>_<name>`` exposing
``fetch(client)``, ``parse()`` and ``validate()``. ``fetch <id>`` resolves by prefix.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import pkgutil
import sys

from courtdelay import sources
from courtdelay.common.http import Client


def _source_modules() -> dict[str, str]:
    return {
        m.name.split("_", 1)[0]: f"{sources.__name__}.{m.name}"
        for m in pkgutil.iter_modules(sources.__path__)
        if not m.name.startswith("_")
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="courtdelay")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="fetch, parse and validate a source")
    f.add_argument("source", help="source id, e.g. s1, or 'all'")
    f.add_argument("--no-fetch", action="store_true", help="parse cached raw files only")
    f.add_argument(
        "--refresh",
        action="store_true",
        help="open-data sources only: request pages again even when cached (pages that "
        "change in place); a failed answer never replaces a good cached copy",
    )
    f.add_argument(
        "--strata", nargs="*", help="docket sources only: run these strata (e.g. FCA-2024)"
    )
    sub.add_parser("list", help="list registered sources")
    sub.add_parser("build", help="build derived aggregate tables")
    r = sub.add_parser("refresh", help="weekly incremental fetch of one docket host")
    r.add_argument(
        "court",
        choices=["fc", "tcc", "scc"],
        help="fc = Federal Court and FCA; tcc = Tax Court; scc = Supreme Court",
    )
    r.add_argument("--max-minutes", type=float, default=None, help="stop cleanly after this long")
    r.add_argument(
        "--new-only",
        action="store_true",
        help="new filings (and Tax Court status changes) only; skip the weekly slice",
    )
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    mods = _source_modules()
    if args.cmd == "list":
        for sid, mod in sorted(mods.items()):
            print(f"{sid:5s} {mod}")
        return 0
    if args.cmd == "refresh":
        from courtdelay import refresh

        row = refresh.run_refresh(args.court, max_minutes=args.max_minutes, new_only=args.new_only)
        return 0 if row["status"] == "ok" else 1
    if args.cmd == "build":
        from courtdelay.estimate.build import build_all

        build_all()
        return 0
    if args.source == "all":
        # Tier 2 crawls run for days; they only start when named explicitly
        ids = [
            sid
            for sid in sorted(mods)
            if getattr(importlib.import_module(mods[sid]), "TIER", 1) < 2
        ]
    else:
        ids = [args.source.lower()]
    with Client(refresh_tier1=args.refresh) as client:
        for sid in ids:
            if sid not in mods:
                print(f"unknown source {sid!r}; known: {', '.join(sorted(mods))}", file=sys.stderr)
                return 2
            mod = importlib.import_module(mods[sid])
            if not args.no_fetch:
                if args.strata:
                    mod.fetch(client, strata=args.strata)
                else:
                    mod.fetch(client)
            tidy = mod.parse()
            mod.validate(tidy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

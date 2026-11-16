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
    sub.add_parser("list", help="list registered sources")
    sub.add_parser("build", help="build processed outputs (not yet implemented)")
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
    if args.cmd == "build":
        print("build: not yet implemented (M2)")
        return 0
    ids = sorted(mods) if args.source == "all" else [args.source.lower()]
    with Client() as client:
        for sid in ids:
            if sid not in mods:
                print(f"unknown source {sid!r}; known: {', '.join(sorted(mods))}", file=sys.stderr)
                return 2
            mod = importlib.import_module(mods[sid])
            if not args.no_fetch:
                mod.fetch(client)
            tidy = mod.parse()
            mod.validate(tidy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

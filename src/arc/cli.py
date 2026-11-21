from __future__ import annotations

import argparse
import datetime as dt
import sys

from . import __version__
from .checks import run_check
from .report import FORMATS


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="arc", description="Release checks for n8n workflows and Apps Script projects")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="check one or more automation folders")
    c.add_argument("paths", nargs="+", metavar="DIR",
                   help="folder of n8n workflow JSON files, or a clasp-pulled Apps Script project")
    c.add_argument("--manifest", default="governance.yml")
    c.add_argument("--rules", default="rules.yml")
    c.add_argument("--format", choices=sorted(FORMATS), default="text")
    c.add_argument("--today", help="treat this YYYY-MM-DD as today (tests and reruns)")
    args = p.parse_args(argv)

    today = None
    if args.today:
        try:
            today = dt.date.fromisoformat(args.today)
        except ValueError:
            p.error("--today must be YYYY-MM-DD")
    findings = run_check(args.paths, args.manifest, args.rules, today)
    sys.stdout.write(FORMATS[args.format](findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())

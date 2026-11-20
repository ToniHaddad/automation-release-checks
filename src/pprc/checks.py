"""The governance checks."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from .config import Manifest, Rules, load_manifest, load_rules, parse_date
from .models import Finding
from .solution import Solution, load_solution


def check_connectors(sol: Solution, rules: Rules) -> list[Finding]:
    out, seen = [], set()
    for use in sol.connectors:
        if use.connector in rules.approved_connectors:
            continue
        key = (use.connector, use.file)
        if key in seen:
            continue
        seen.add(key)
        out.append(Finding(
            "PPRC001",
            f"Connector '{use.connector}' (used by {use.where}) is not on the approved list.",
            f"Remove the '{use.connector}' action, or ask the governance owner to review it "
            "and add it to approved_connectors in the rules file.",
            use.file, use.line))
    return out


def check_manifest_entry(sol: Solution, manifest: Manifest, rules: Rules,
                         today: dt.date) -> list[Finding]:
    name = sol.unique_name
    if name is None:
        return []  # already reported as a file problem
    mf = manifest.path
    entry = manifest.solutions.get(name)
    if entry is None:
        return [Finding(
            "PPRC002", f"Solution '{name}' has no entry in the governance manifest, so no owner.",
            f"Add a '{name}:' entry under solutions: with owner, data_classification "
            "and review_date.", mf, 1)]
    out = []
    at = entry.lines
    if not entry.owner or not entry.owner.strip():
        out.append(Finding(
            "PPRC002", f"Solution '{name}' has no business owner.",
            "Set owner to the named person or role accountable for this solution.",
            mf, at.get("owner") or at.get("solution")))
    cls = (entry.classification or "").strip().lower()
    if cls not in rules.classifications:
        shown = f"'{entry.classification}'" if entry.classification else "missing"
        out.append(Finding(
            "PPRC004", f"Data classification for '{name}' is {shown}; "
            f"allowed: {', '.join(rules.classifications)}.",
            "Set data_classification to one of the allowed values.",
            mf, at.get("data_classification") or at.get("solution")))
    line = at.get("review_date") or at.get("solution")
    if entry.review_date is None:
        out.append(Finding(
            "PPRC003", f"Solution '{name}' has no review date.",
            "Add review_date: YYYY-MM-DD, the date the next governance review is due.",
            mf, line))
    else:
        d = parse_date(entry.review_date)
        if d is None:
            out.append(Finding(
                "PPRC003",
                f"review_date '{entry.review_date}' for '{name}' is not a YYYY-MM-DD date.",
                "Write the date as YYYY-MM-DD.", mf, line))
        elif d < today:
            out.append(Finding(
                "PPRC003",
                f"Review for '{name}' was due {d.isoformat()} ({(today - d).days} days overdue).",
                "Hold the governance review, then move review_date forward.", mf, line))
    return out


def run_check(solution_dir: str, manifest_path: str, rules_path: str,
              today: dt.date | None = None) -> list[Finding]:
    today = today or dt.date.today()
    findings: list[Finding] = []
    rules, f = load_rules(Path(rules_path), rules_path.replace("\\", "/"))
    findings += f
    manifest, f = load_manifest(Path(manifest_path), manifest_path.replace("\\", "/"))
    findings += f
    sol = load_solution(Path(solution_dir), solution_dir.replace("\\", "/").rstrip("/"))
    findings += sol.findings
    if rules:
        findings += check_connectors(sol, rules)
    if manifest and rules:
        findings += check_manifest_entry(sol, manifest, rules, today)
    return findings

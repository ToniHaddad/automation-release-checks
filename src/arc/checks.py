"""The governance checks."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from .config import AutomationEntry, Manifest, Rules, load_manifest, load_rules, parse_date
from .loaders import Automation, load_automation
from .models import Finding


def check_facts(auto: Automation, rules: Rules) -> list[Finding]:
    out: list[Finding] = []
    seen: set[tuple] = set()
    for f in auto.facts:
        if f.kind == "node_type" and f.value not in rules.node_types:
            key = ("ARC001", f.value, f.file)
            if key not in seen:
                seen.add(key)
                out.append(Finding(
                    "ARC001", f"n8n node type '{f.value}' ({f.where}) is not on the approved list.",
                    f"Replace the node with an approved one, or ask the owner of rules.yml to review "
                    f"'{f.value}' and add it to approved_n8n_node_types.", f.file, f.line))
        elif f.kind == "credential_type" and f.value not in rules.credential_types:
            key = ("ARC002", f.value, f.file)
            if key not in seen:
                seen.add(key)
                out.append(Finding(
                    "ARC002", f"n8n credential type '{f.value}' ({f.where}) is not on the approved list.",
                    f"Use an approved credential type, or have '{f.value}' reviewed and added to "
                    "approved_n8n_credential_types.", f.file, f.line))
        elif f.kind == "oauth_scope" and f.value not in rules.oauth_scopes:
            key = ("ARC003", f.value, f.file)
            if key not in seen:
                seen.add(key)
                out.append(Finding(
                    "ARC003", f"Apps Script OAuth scope '{f.value}' is not on the approved list.",
                    "Remove the scope and the code that needs it, or have it reviewed and added to "
                    "approved_oauth_scopes.", f.file, f.line))
        elif f.kind == "secret":
            key = ("ARC020", f.file, f.line)
            if key not in seen:
                seen.add(key)
                out.append(Finding(
                    "ARC020", f"Hardcoded secret: {f.value}.",
                    "Move it to an n8n credential, or to Script Properties in Apps Script, "
                    "and rotate it because it is now in the repository history.", f.file, f.line))
        elif f.kind == "email":
            key = ("ARC021", f.file, f.line, f.value)
            if key not in seen:
                seen.add(key)
                out.append(Finding(
                    "ARC021", f"Hardcoded email address: {f.value}.",
                    "Read recipients from the sheet or a Script Property, or add a shared role mailbox "
                    "to allowed_email_addresses in the rules file.", f.file, f.line))
        elif f.kind == "no_error_workflow":
            out.append(Finding(
                "ARC030", f"{f.where[0].upper()}{f.where[1:]} is active with a schedule trigger but has no error workflow.",
                "In the workflow settings choose an Error workflow (one that starts with an Error Trigger), "
                "so a failed run notifies someone.", f.file, f.line))
    return out


def check_manifest_entry(auto: Automation, manifest: Manifest, rules: Rules,
                         today: dt.date) -> list[Finding]:
    name = auto.name
    mf = manifest.path
    entry: AutomationEntry | None = manifest.automations.get(name)
    if entry is None:
        return [Finding(
            "ARC010", f"Automation '{name}' has no entry in the governance manifest, so no owner.",
            f"Add a '{name}:' entry under automations: with owner, data_classification and review_date.",
            mf, 1)]
    out = []
    at = entry.lines
    anchor = at.get("entry")
    if not entry.owner or not entry.owner.strip():
        out.append(Finding(
            "ARC010", f"Automation '{name}' has no business owner.",
            "Set owner to the named person or role accountable for this automation.",
            mf, at.get("owner") or anchor))
    cls = (entry.classification or "").strip().lower()
    if cls not in rules.classifications:
        shown = f"'{entry.classification}'" if entry.classification else "missing"
        out.append(Finding(
            "ARC012", f"Data classification for '{name}' is {shown}; "
            f"allowed: {', '.join(rules.classifications)}.",
            "Set data_classification to one of the allowed values.",
            mf, at.get("data_classification") or anchor))
    line = at.get("review_date") or anchor
    if entry.review_date is None:
        out.append(Finding(
            "ARC011", f"Automation '{name}' has no review date.",
            "Add review_date: YYYY-MM-DD, the date the next review is due.", mf, line))
    else:
        d = parse_date(entry.review_date)
        if d is None:
            out.append(Finding(
                "ARC011", f"review_date '{entry.review_date}' for '{name}' is not a YYYY-MM-DD date.",
                "Write the date as YYYY-MM-DD.", mf, line))
        elif d < today:
            out.append(Finding(
                "ARC011",
                f"Review for '{name}' was due {d.isoformat()} ({(today - d).days} days overdue).",
                "Hold the review, then move review_date forward.", mf, line))
    return out


def run_check(paths: list[str], manifest_path: str, rules_path: str,
              today: dt.date | None = None) -> list[Finding]:
    today = today or dt.date.today()
    findings: list[Finding] = []
    rules, f = load_rules(Path(rules_path), rules_path.replace("\\", "/"))
    findings += f
    manifest, f = load_manifest(Path(manifest_path), manifest_path.replace("\\", "/"))
    findings += f
    for raw in paths:
        shown = raw.replace("\\", "/").rstrip("/") or "."
        auto = load_automation(Path(raw), shown, rules.allowed_emails if rules else frozenset())
        findings += auto.findings
        if not Path(raw).is_dir():
            continue
        if rules:
            findings += check_facts(auto, rules)
        if manifest and rules:
            findings += check_manifest_entry(auto, manifest, rules, today)
    return findings

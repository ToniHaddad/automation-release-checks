from __future__ import annotations

import json

from .models import RULE_TITLES, Finding


def _loc(f: Finding) -> str:
    return f"{f.file}:{f.line}" if f.line else f.file


def as_text(findings: list[Finding]) -> str:
    if not findings:
        return "OK: no findings.\n"
    lines = []
    for f in findings:
        lines.append(f"{f.rule}  {_loc(f)}")
        lines.append(f"    {f.message}")
        lines.append(f"    Fix: {f.remediation}")
    n = len(findings)
    lines.append("")
    lines.append(f"FAILED: {n} finding{'s' if n != 1 else ''}.")
    return "\n".join(lines) + "\n"


def as_json(findings: list[Finding]) -> str:
    return json.dumps({
        "ok": not findings,
        "count": len(findings),
        "findings": [dict(f.to_dict(), title=RULE_TITLES.get(f.rule, "")) for f in findings],
    }, indent=2) + "\n"


def _esc_data(s: str) -> str:
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _esc_prop(s: str) -> str:
    return _esc_data(s).replace(":", "%3A").replace(",", "%2C")


def as_github(findings: list[Finding]) -> str:
    out = []
    for f in findings:
        props = f"file={_esc_prop(f.file)}"
        if f.line:
            props += f",line={f.line}"
        props += f",title={_esc_prop(f.rule + ' ' + RULE_TITLES.get(f.rule, ''))}"
        out.append(f"::error {props}::{_esc_data(f.message + ' Fix: ' + f.remediation)}")
    n = len(findings)
    out.append(f"pprc: FAILED, {n} finding(s)" if n else "pprc: OK, no findings")
    return "\n".join(out) + "\n"


FORMATS = {"text": as_text, "json": as_json, "github": as_github}

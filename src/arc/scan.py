"""Find hardcoded secrets and email addresses in a piece of text."""
from __future__ import annotations

import re
from dataclasses import dataclass

SECRET_WORD = r"(?:api[_-]?key|token|secret|passw(?:or)?d|authorization|private[_-]?key)"

# name = "literal"  /  "name": "literal"  where the name ends in a secret-like word
ASSIGNMENT = re.compile(
    r"""(?ix)
    (?P<name>[A-Za-z0-9_.\-]*?""" + SECRET_WORD + r""")
    ["']?\s*[:=]\s*
    ["'](?P<value>[^"'\s]{8,})["']
    """)
BEARER = re.compile(r"(?i)\bbearer\s+(?P<value>[A-Za-z0-9._\-]{16,})")
KNOWN = [
    ("a GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("a Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("an AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("a Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("an API secret key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("a JSON web token", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b")),
    ("a private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]
EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}\b")
PLACEHOLDER = re.compile(r"(?i)^(<.*>|\{\{.*\}\}|\$\{.*\}|x{4,}|\*{4,}|your[_-].*|changeme|example|placeholder)$")


@dataclass(frozen=True)
class Hit:
    kind: str       # "secret" or "email"
    what: str       # human description, never the secret itself
    line: int       # 1-based line inside the scanned text


def mask(value: str) -> str:
    return f"{value[:3]}... ({len(value)} characters)"


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def is_placeholder(value: str) -> bool:
    return bool(PLACEHOLDER.match(value))


def scan_text(text: str, allowed_emails: set[str] | frozenset[str] = frozenset()) -> list[Hit]:
    hits: list[Hit] = []
    seen_spans: list[tuple[int, int]] = []

    def add(kind, what, start, end):
        if any(s <= start < e for s, e in seen_spans):
            return
        seen_spans.append((start, end))
        hits.append(Hit(kind, what, _line(text, start)))

    for label, rx in KNOWN:
        for m in rx.finditer(text):
            add("secret", f"looks like {label} ({mask(m.group(0))})", m.start(), m.end())
    for m in BEARER.finditer(text):
        if not is_placeholder(m.group("value")):
            add("secret", f"a literal bearer token ({mask(m.group('value'))})", m.start(), m.end())
    for m in ASSIGNMENT.finditer(text):
        if not is_placeholder(m.group("value")):
            add("secret", f"'{m.group('name')}' is set to a literal value ({mask(m.group('value'))})",
                m.start(), m.end())
    for m in EMAIL.finditer(text):
        if m.group(0).lower() not in allowed_emails:
            add("email", f"the address {m.group(0)}", m.start(), m.end())
    return hits


def secret_key(name: str) -> bool:
    return bool(re.search(r"(?i)" + SECRET_WORD + r"$", name.strip()))

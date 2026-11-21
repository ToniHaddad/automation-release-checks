from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Finding:
    rule: str
    message: str
    remediation: str
    file: str
    line: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Fact:
    """Something a loader saw in a file. Checks turn facts into findings."""
    kind: str  # node_type, credential_type, oauth_scope, secret, email, no_error_workflow
    value: str
    file: str
    line: int | None
    where: str


RULE_TITLES = {
    "ARC001": "n8n node type not on the allowlist",
    "ARC002": "n8n credential type not on the allowlist",
    "ARC003": "Apps Script OAuth scope not on the allowlist",
    "ARC010": "No business owner",
    "ARC011": "Review overdue or missing",
    "ARC012": "Data classification missing or invalid",
    "ARC020": "Hardcoded secret",
    "ARC021": "Hardcoded email address",
    "ARC030": "Scheduled workflow has no error workflow",
    "ARC100": "Folder or file missing",
    "ARC101": "File could not be parsed",
    "ARC102": "File has an unexpected structure",
    "ARC103": "Governance manifest problem",
    "ARC104": "Rules file problem",
}

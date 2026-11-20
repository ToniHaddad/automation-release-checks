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


RULE_TITLES = {
    "PPRC001": "Connector not on the allowlist",
    "PPRC002": "No business owner",
    "PPRC003": "Review overdue or missing",
    "PPRC004": "Data classification missing or invalid",
    "PPRC100": "Solution folder or file missing",
    "PPRC101": "File could not be parsed",
    "PPRC102": "File has an unexpected structure",
    "PPRC103": "Governance manifest problem",
    "PPRC104": "Rules file problem",
}

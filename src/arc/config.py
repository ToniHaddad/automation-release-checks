"""Load the rules file and the governance manifest."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .lines import yaml_key_lines
from .models import Finding

DEFAULT_CLASSIFICATIONS = ["public", "internal", "confidential", "restricted"]


@dataclass
class Rules:
    node_types: set[str]
    credential_types: set[str]
    oauth_scopes: set[str]
    allowed_emails: frozenset[str] = frozenset()
    classifications: list[str] = field(default_factory=lambda: list(DEFAULT_CLASSIFICATIONS))


@dataclass
class AutomationEntry:
    owner: str | None
    classification: str | None
    review_date: object  # date, str or None
    lines: dict[str, int | None]


@dataclass
class Manifest:
    path: str
    automations: dict[str, AutomationEntry]


def _load_yaml(path: Path, shown: str, rule: str, what: str):
    """Return (data, lines, finding)."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        return None, {}, Finding(rule, f"Cannot read {what} {shown}: {e.strerror or e}",
                                 f"Create {shown} or pass the right path.", shown)
    except UnicodeDecodeError:
        return None, {}, Finding(rule, f"The {what} is not valid UTF-8.",
                                 "Save the file as UTF-8.", shown)
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        return None, {}, Finding(rule, f"The {what} is not valid YAML: "
                                 f"{getattr(e, 'problem', e)}",
                                 "Fix the YAML syntax at the reported line.", shown,
                                 mark.line + 1 if mark else None)
    return data, yaml_key_lines(text), None


LIST_KEYS = {
    "approved_n8n_node_types": "node_types",
    "approved_n8n_credential_types": "credential_types",
    "approved_oauth_scopes": "oauth_scopes",
}


def load_rules(path: Path, shown: str) -> tuple[Rules | None, list[Finding]]:
    data, lines, err = _load_yaml(path, shown, "ARC104", "rules file")
    if err:
        return None, [err]
    if not isinstance(data, dict):
        return None, [Finding("ARC104", "Rules file must be a YAML mapping.",
                              "Add the three approved_* lists; see rules.yml in the repository.", shown, 1)]
    out: dict[str, set[str]] = {}
    for key, attr in LIST_KEYS.items():
        val = data.get(key)
        if not isinstance(val, list) or not all(isinstance(v, str) for v in val):
            return None, [Finding(
                "ARC104", f"Rules file needs '{key}' as a list of strings.",
                f"Add {key}: [...] to the rules file (an empty list approves nothing).",
                shown, lines.get((key,), 1))]
        out[attr] = {v.strip() for v in val}
    emails = data.get("allowed_email_addresses", [])
    if not isinstance(emails, list) or not all(isinstance(v, str) for v in emails):
        return None, [Finding("ARC104", "'allowed_email_addresses' must be a list of strings.",
                              "Fix the list or remove the key.", shown,
                              lines.get(("allowed_email_addresses",), 1))]
    rules = Rules(out["node_types"], out["credential_types"], out["oauth_scopes"],
                  frozenset(e.strip().lower() for e in emails))
    cls = data.get("data_classifications")
    if isinstance(cls, list) and cls and all(isinstance(c, str) for c in cls):
        rules.classifications = [c.lower() for c in cls]
    return rules, []


def load_manifest(path: Path, shown: str) -> tuple[Manifest | None, list[Finding]]:
    data, lines, err = _load_yaml(path, shown, "ARC103", "governance manifest")
    if err:
        return None, [err]
    sols = data.get("automations") if isinstance(data, dict) else None
    if not isinstance(sols, dict):
        return None, [Finding(
            "ARC103",
            "Governance manifest must have a 'automations' mapping keyed by the automation folder name.",
            "See governance.yml in the repository for the expected shape.", shown,
            lines.get(("automations",), 1))]
    out: dict[str, AutomationEntry] = {}
    for name, body in sols.items():
        body = body if isinstance(body, dict) else {}
        key = ("automations", str(name))
        owner = body.get("owner")
        cls = body.get("data_classification")
        out[str(name)] = AutomationEntry(
            owner=owner if isinstance(owner, str) else None,
            classification=cls if isinstance(cls, str) else None,
            review_date=body.get("review_date"),
            lines={
                "entry": lines.get(key),
                "owner": lines.get(key + ("owner",)),
                "data_classification": lines.get(key + ("data_classification",)),
                "review_date": lines.get(key + ("review_date",)),
            })
    return Manifest(shown, out), []


def parse_date(value) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None

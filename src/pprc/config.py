"""Load the rules file and the governance manifest."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .lines import yaml_key_lines
from .models import Finding
from .solution import normalise_connector

DEFAULT_CLASSIFICATIONS = ["public", "internal", "confidential", "restricted"]


@dataclass
class Rules:
    approved_connectors: set[str]
    classifications: list[str] = field(default_factory=lambda: list(DEFAULT_CLASSIFICATIONS))


@dataclass
class SolutionEntry:
    owner: str | None
    classification: str | None
    review_date: object  # date, str or None
    lines: dict[str, int | None]


@dataclass
class Manifest:
    path: str
    solutions: dict[str, SolutionEntry]


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


def load_rules(path: Path, shown: str) -> tuple[Rules | None, list[Finding]]:
    data, lines, err = _load_yaml(path, shown, "PPRC104", "rules file")
    if err:
        return None, [err]
    ok = (isinstance(data, dict) and isinstance(data.get("approved_connectors"), list)
          and all(isinstance(c, str) for c in data["approved_connectors"]))
    if not ok:
        return None, [Finding(
            "PPRC104", "Rules file must be a mapping with an 'approved_connectors' list of strings.",
            "Add approved_connectors: [shared_sharepointonline, ...] to the rules file.",
            shown, lines.get(("approved_connectors",), 1))]
    rules = Rules({normalise_connector(c) for c in data["approved_connectors"]})
    cls = data.get("data_classifications")
    if isinstance(cls, list) and cls and all(isinstance(c, str) for c in cls):
        rules.classifications = [c.lower() for c in cls]
    return rules, []


def load_manifest(path: Path, shown: str) -> tuple[Manifest | None, list[Finding]]:
    data, lines, err = _load_yaml(path, shown, "PPRC103", "governance manifest")
    if err:
        return None, [err]
    sols = data.get("solutions") if isinstance(data, dict) else None
    if not isinstance(sols, dict):
        return None, [Finding(
            "PPRC103",
            "Governance manifest must have a 'solutions' mapping keyed by solution unique name.",
            "See governance.yml in the repository for the expected shape.", shown,
            lines.get(("solutions",), 1))]
    out: dict[str, SolutionEntry] = {}
    for name, body in sols.items():
        body = body if isinstance(body, dict) else {}
        key = ("solutions", str(name))
        owner = body.get("owner")
        cls = body.get("data_classification")
        out[str(name)] = SolutionEntry(
            owner=owner if isinstance(owner, str) else None,
            classification=cls if isinstance(cls, str) else None,
            review_date=body.get("review_date"),
            lines={
                "solution": lines.get(key),
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

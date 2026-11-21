"""Read an automation folder: n8n workflow exports and/or an Apps Script project (clasp layout)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .jsonlines import JSONLineError, parse
from .models import Fact, Finding
from .scan import is_placeholder, mask, scan_text, secret_key

SCHEDULE_TYPES = {"n8n-nodes-base.scheduleTrigger", "n8n-nodes-base.cron", "n8n-nodes-base.interval"}
SKIP_DIRS = {"node_modules", ".git", ".clasp", "__pycache__"}


@dataclass
class Automation:
    name: str
    facts: list[Fact] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


def _files(root: Path, suffixes: tuple[str, ...]):
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in suffixes \
                and not any(part in SKIP_DIRS or part.startswith(".") for part in p.relative_to(root).parts):
            yield p


def _read(path: Path, shown: str, auto: Automation) -> str | None:
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as e:
        auto.findings.append(Finding(
            "ARC100", f"Cannot read {shown}: {e.strerror or e}",
            "Check the file exists and is readable.", shown))
    except UnicodeDecodeError:
        auto.findings.append(Finding(
            "ARC101", f"{shown} is not valid UTF-8 text.",
            "Re-export or re-pull the file and save it as UTF-8.", shown))
    return None


def load_automation(root: Path, shown: str, allowed_emails: frozenset[str]) -> Automation:
    auto = Automation(name=root.resolve().name)
    if not root.is_dir():
        auto.findings.append(Finding(
            "ARC100", f"Automation folder not found: {shown}",
            "Pass the folder holding the n8n workflow JSON files or the clasp-pulled Apps Script project.",
            shown))
        return auto
    has_manifest = (root / "appsscript.json").is_file()
    code_files = list(_files(root, (".gs", ".js")))
    json_files = [p for p in _files(root, (".json",)) if p.name != "appsscript.json"]
    n8n_files = [] if has_manifest else json_files
    if not has_manifest and not n8n_files:
        auto.findings.append(Finding(
            "ARC100",
            f"No n8n workflow JSON and no appsscript.json found in {shown}.",
            "Point arc at a folder of exported n8n workflows or a clasp pull of an Apps Script project.",
            shown))
        return auto
    for p in n8n_files:
        _load_workflow(p, f"{shown}/{p.relative_to(root).as_posix()}", auto, allowed_emails)
    if has_manifest:
        _load_apps_script(root, shown, code_files, auto, allowed_emails)
    return auto


# ---------------------------------------------------------------- n8n

def _load_workflow(path: Path, shown: str, auto: Automation, allowed: frozenset[str]) -> None:
    text = _read(path, shown, auto)
    if text is None:
        return
    try:
        data, lines = parse(text)
    except JSONLineError as e:
        auto.findings.append(Finding(
            "ARC101", f"{path.name} is not valid JSON: {e.msg}",
            "Re-export the workflow from n8n, or repair the JSON at the reported line.", shown, e.line))
        return
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), list):
        auto.findings.append(Finding(
            "ARC102", f"{path.name} does not look like an n8n workflow export (no 'nodes' list).",
            "Export the workflow with Download in the n8n workflow menu.", shown, 1))
        return
    wf_name = data.get("name") if isinstance(data.get("name"), str) else path.stem
    has_schedule = False
    for i, node in enumerate(data["nodes"]):
        at = ("nodes", i)
        if not isinstance(node, dict) or not isinstance(node.get("type"), str):
            auto.findings.append(Finding(
                "ARC102", f"Node {i + 1} in {path.name} has no 'type'.",
                "Re-export the workflow; every node needs a type such as n8n-nodes-base.googleSheets.",
                shown, lines.get(at)))
            continue
        name = node.get("name") if isinstance(node.get("name"), str) else f"node {i + 1}"
        where = f"node '{name}' in workflow '{wf_name}'"
        ntype = node["type"]
        auto.facts.append(Fact("node_type", ntype, shown, lines.get(at + ("type",)), where))
        has_schedule = has_schedule or ntype in SCHEDULE_TYPES
        creds = node.get("credentials")
        if isinstance(creds, dict):
            for ctype in creds:
                auto.facts.append(Fact("credential_type", ctype, shown,
                                       lines.get(at + ("credentials", ctype)), where))
        _scan_params(node.get("parameters"), at + ("parameters",), (), shown, lines, where, auto, allowed)
    if data.get("active") is True and has_schedule:
        settings = data.get("settings")
        err = settings.get("errorWorkflow") if isinstance(settings, dict) else None
        if not (isinstance(err, str) and err.strip()):
            line = lines.get(("settings",)) or lines.get(("active",))
            auto.facts.append(Fact("no_error_workflow", wf_name, shown, line,
                                   f"workflow '{wf_name}'"))


def _scan_params(node, path, keys, shown, lines, where, auto, allowed) -> None:
    """Walk n8n node parameters. `keys` is the chain of dict keys above this value."""
    line = lines.get(path)
    if isinstance(node, dict):
        # header/query parameter entries look like {"name": "Authorization", "value": "Bearer ..."}
        pname, pval = node.get("name"), node.get("value")
        if isinstance(pname, str) and isinstance(pval, str) and secret_key(pname):
            _literal_secret(pname, pval, shown, lines.get(path + ("value",)) or line, where, auto)
        for k, v in node.items():
            _scan_params(v, path + (k,), keys + (str(k),), shown, lines, where, auto, allowed)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _scan_params(v, path + (i,), keys, shown, lines, where, auto, allowed)
    elif isinstance(node, str):
        if keys and secret_key(keys[-1]) and keys[-1] not in ("name", "value"):
            _literal_secret(keys[-1], node, shown, line, where, auto)
        for h in scan_text(node, allowed):
            what = f"{h.what} in {where}"
            auto.facts.append(Fact(h.kind, what, shown, line, where))


def _literal_secret(name, value, shown, line, where, auto) -> None:
    if value.startswith("=") or len(value) < 8 or is_placeholder(value):
        return  # an n8n expression, or too short or empty to be a real value
    auto.facts.append(Fact("secret", f"parameter '{name}' in {where} holds a literal value ({mask(value)})",
                           shown, line, where))


# ---------------------------------------------------------------- Apps Script

def _load_apps_script(root: Path, shown: str, code_files, auto: Automation, allowed) -> None:
    mpath = root / "appsscript.json"
    mshown = f"{shown}/appsscript.json"
    text = _read(mpath, mshown, auto)
    if text is not None:
        try:
            data, lines = parse(text)
        except JSONLineError as e:
            auto.findings.append(Finding(
                "ARC101", f"appsscript.json is not valid JSON: {e.msg}",
                "Run clasp pull again, or repair the JSON at the reported line.", mshown, e.line))
            data = None
        if data is not None:
            _check_manifest(data, lines, mshown, auto)
    for p in code_files:
        cshown = f"{shown}/{p.relative_to(root).as_posix()}"
        src = _read(p, cshown, auto)
        if src is None:
            continue
        for h in scan_text(src, allowed):
            auto.facts.append(Fact(h.kind, f"{h.what} in {p.name}", cshown, h.line, f"{p.name}"))


def _check_manifest(data, lines, mshown, auto) -> None:
    if not isinstance(data, dict):
        auto.findings.append(Finding(
            "ARC102", "appsscript.json is not a JSON object.",
            "Run clasp pull to restore the manifest.", mshown, 1))
        return
    scopes = data.get("oauthScopes")
    if scopes is None:
        auto.findings.append(Finding(
            "ARC102",
            "appsscript.json has no explicit oauthScopes, so Google infers the scopes at run time "
            "and a static scan cannot check them.",
            "Add an oauthScopes list naming each scope the script needs.", mshown, 1))
        return
    if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
        auto.findings.append(Finding(
            "ARC102", "oauthScopes must be a list of strings.",
            "Write oauthScopes as a list of scope URLs.", mshown, lines.get(("oauthScopes",))))
        return
    for i, s in enumerate(scopes):
        auto.facts.append(Fact("oauth_scope", s, mshown, lines.get(("oauthScopes", i)), "appsscript.json"))

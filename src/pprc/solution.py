"""Read an unpacked Power Platform solution (pac solution unpack layout)."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .lines import find_line
from .models import Finding

PROVIDER_PREFIX = "/providers/microsoft.powerapps/apis/"


def normalise_connector(raw: str) -> str:
    """'/providers/Microsoft.PowerApps/apis/shared_x' -> 'shared_x' (lowercase)."""
    value = raw.strip().lower()
    if value.startswith(PROVIDER_PREFIX):
        value = value[len(PROVIDER_PREFIX):]
    return value.rstrip("/").rsplit("/", 1)[-1]


@dataclass
class ConnectorUse:
    connector: str
    raw: str
    file: str
    line: int | None
    where: str


@dataclass
class Solution:
    path: Path
    unique_name: str | None = None
    connectors: list[ConnectorUse] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


def _read(path: Path, sol: Solution, display: str) -> str | None:
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as e:
        sol.findings.append(Finding(
            "PPRC100", f"Cannot read {display}: {e.strerror or e}",
            "Check the file exists and is readable, then unpack the solution again.",
            display))
    except UnicodeDecodeError:
        sol.findings.append(Finding(
            "PPRC101", f"{display} is not valid UTF-8 text.",
            "Re-export and unpack the solution with pac solution unpack.", display))
    return None


def _xml_error_line(err: ET.ParseError) -> int | None:
    pos = getattr(err, "position", None)
    return pos[0] if pos else None


def _parse_xml(text: str, display: str, sol: Solution):
    try:
        return ET.fromstring(text)
    except ET.ParseError as e:
        sol.findings.append(Finding(
            "PPRC101", f"{display.rsplit('/', 1)[-1]} is not well-formed XML: {e}",
            "Re-run pac solution unpack from a fresh export, or repair the XML by hand.",
            display, _xml_error_line(e)))
        return None


def load_solution(root: Path, shown: str | None = None) -> Solution:
    sol = Solution(path=root)
    shown = shown or str(root).replace("\\", "/")

    def disp(rel: str) -> str:
        return f"{shown}/{rel}"

    if not root.is_dir():
        sol.findings.append(Finding(
            "PPRC100", f"Solution folder not found: {shown}",
            "Pass the folder produced by pac solution unpack (it contains Other/Solution.xml).",
            shown))
        return sol

    _load_solution_xml(root, sol, disp)
    _load_customizations(root, sol, disp)
    _load_workflows(root, sol, disp)
    return sol


def _load_solution_xml(root: Path, sol: Solution, disp) -> None:
    rel = "Other/Solution.xml"
    path = root / "Other" / "Solution.xml"
    d = disp(rel)
    if not path.is_file():
        sol.findings.append(Finding(
            "PPRC100", f"{rel} is missing; this is not an unpacked solution.",
            "Run pac solution unpack and point pprc at the output folder.", d))
        return
    text = _read(path, sol, d)
    if text is None:
        return
    xml = _parse_xml(text, d, sol)
    if xml is None:
        return
    node = xml.find("./SolutionManifest/UniqueName")
    if node is None or not (node.text or "").strip():
        sol.findings.append(Finding(
            "PPRC102", "Solution.xml has no SolutionManifest/UniqueName.",
            "Re-export the solution; the unique name identifies it in governance.yml.",
            d, find_line(text, "<SolutionManifest") or 1))
        return
    sol.unique_name = node.text.strip()


def _load_customizations(root: Path, sol: Solution, disp) -> None:
    rel = "Other/Customizations.xml"
    path = root / "Other" / "Customizations.xml"
    d = disp(rel)
    if not path.is_file():
        sol.findings.append(Finding(
            "PPRC100", f"{rel} is missing.",
            "Re-run pac solution unpack; Customizations.xml holds the connection references.", d))
        return
    text = _read(path, sol, d)
    if text is None:
        return
    xml = _parse_xml(text, d, sol)
    if xml is None:
        return
    if xml.tag != "ImportExportXml":
        sol.findings.append(Finding(
            "PPRC102", f"Root element is <{xml.tag}>, expected <ImportExportXml>.",
            "Use the Customizations.xml written by pac solution unpack.", d, 1))
        return
    for ref in xml.findall("./connectionreferences/connectionreference"):
        logical = ref.get("connectionreferencelogicalname", "")
        cid = ref.find("connectorid")
        anchor = find_line(text, f'"{logical}"') if logical else None
        if cid is None or not (cid.text or "").strip():
            sol.findings.append(Finding(
                "PPRC102",
                f"Connection reference '{logical or '?'}' has no connectorid.",
                "Re-export the solution, or add the connectorid element "
                "(for example /providers/Microsoft.PowerApps/apis/shared_sharepointonline).",
                d, anchor))
            continue
        raw = cid.text.strip()
        line = find_line(text, raw, (anchor or 1) - 1)
        sol.connectors.append(ConnectorUse(
            normalise_connector(raw), raw, d, line,
            f"connection reference '{logical}'"))


def _load_workflows(root: Path, sol: Solution, disp) -> None:
    wf_dir = root / "Workflows"
    if not wf_dir.is_dir():
        return  # a solution without flows is valid
    for path in sorted(wf_dir.glob("*.json")):
        d = disp(f"Workflows/{path.name}")
        text = _read(path, sol, d)
        if text is None:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            sol.findings.append(Finding(
                "PPRC101", f"{path.name} is not valid JSON: {e.msg}",
                "Re-export the flow, or repair the JSON syntax at the reported line.",
                d, e.lineno))
            continue
        props = data.get("properties") if isinstance(data, dict) else None
        if not isinstance(props, dict):
            sol.findings.append(Finding(
                "PPRC102", "Flow JSON has no 'properties' object.",
                "Use the flow definition file written by pac solution unpack.", d, 1))
            continue
        refs = props.get("connectionReferences", {})
        if not isinstance(refs, dict):
            sol.findings.append(Finding(
                "PPRC102", "'connectionReferences' is not an object.",
                "Re-export the flow; connectionReferences maps connector names to references.",
                d, find_line(text, '"connectionReferences"')))
            continue
        base = find_line(text, '"connectionReferences"') or 1
        for key, ref in refs.items():
            api = ref.get("api") if isinstance(ref, dict) else None
            name = api.get("name") if isinstance(api, dict) else None
            raw = name if isinstance(name, str) and name else key
            line = find_line(text, f'"{key}"', base)
            sol.connectors.append(ConnectorUse(
                normalise_connector(raw), raw, d, line,
                f"flow '{path.stem}'"))

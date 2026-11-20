import datetime as dt
import json
import shutil
from pathlib import Path

import pytest

from pprc.checks import run_check
from pprc.cli import main
from pprc.report import as_github, as_json
from pprc.solution import normalise_connector

ROOT = Path(__file__).resolve().parent.parent
TODAY = dt.date(2026, 11, 20)


def check(solution, manifest="governance.yml", rules="rules.yml"):
    return run_check(str(ROOT / solution), str(ROOT / manifest), str(ROOT / rules), TODAY)


def rules_of(findings):
    return sorted(f.rule for f in findings)


def test_compliant_has_no_findings():
    assert check("samples/compliant") == []


def test_live_solution_has_no_findings():
    assert check("solutions/field-reporting") == []


def test_noncompliant_hits_each_governance_rule():
    findings = check("samples/noncompliant")
    assert rules_of(findings) == ["PPRC001", "PPRC001", "PPRC002", "PPRC003"]
    overdue = next(f for f in findings if f.rule == "PPRC003")
    assert "2025-01-31" in overdue.message and overdue.line == 16


def test_unapproved_connector_names_file_and_line():
    findings = [f for f in check("samples/noncompliant") if f.rule == "PPRC001"]
    files = {f.file.rsplit("/", 1)[-1]: f.line for f in findings}
    assert files["Customizations.xml"] == 30
    flow = next(v for k, v in files.items() if k.startswith("BackupToDropbox"))
    assert flow == 13
    assert all(f.remediation for f in findings)


def test_malformed_gives_findings_not_traceback():
    findings = check("samples/malformed")
    assert rules_of(findings) == ["PPRC101", "PPRC101"]
    names = {f.file.rsplit("/", 1)[-1].split("-")[0] for f in findings}
    assert names == {"Customizations.xml", "SyncDrafts"}
    assert all(f.line for f in findings)


def test_missing_solution_folder():
    assert rules_of(check("nope")) == ["PPRC100"]


def test_empty_folder_reports_missing_files(tmp_path):
    findings = run_check(str(tmp_path), str(ROOT / "governance.yml"), str(ROOT / "rules.yml"), TODAY)
    assert rules_of(findings) == ["PPRC100", "PPRC100"]


def test_connector_id_normalisation():
    assert normalise_connector("/providers/Microsoft.PowerApps/apis/SHARED_SharePointOnline") == "shared_sharepointonline"
    assert normalise_connector("shared_teams") == "shared_teams"


def _copy_compliant(tmp_path):
    dst = tmp_path / "sol"
    shutil.copytree(ROOT / "samples/compliant", dst)
    return dst


def run_tmp(tmp_path, body):
    sol = _copy_compliant(tmp_path)
    m = tmp_path / "g.yml"
    m.write_text(body, encoding="utf-8")
    return run_check(str(sol), str(m), str(ROOT / "rules.yml"), TODAY)


def test_solution_missing_from_manifest(tmp_path):
    f = run_tmp(tmp_path, "solutions:\n  Other:\n    owner: x\n")
    assert rules_of(f) == ["PPRC002"]


def test_blank_owner_fails(tmp_path):
    f = run_tmp(tmp_path, "solutions:\n  NorthbridgeFieldReporting:\n    owner: '  '\n"
                "    data_classification: internal\n    review_date: 2030-01-01\n")
    assert rules_of(f) == ["PPRC002"]


@pytest.mark.parametrize("date,expect", [
    ("2026-11-19", ["PPRC003"]),
    ("2026-11-20", []),
    ("2026-11-21", []),
    ('"not a date"', ["PPRC003"]),
    ("", ["PPRC003"]),
])
def test_review_date_boundaries(tmp_path, date, expect):
    f = run_tmp(tmp_path, "solutions:\n  NorthbridgeFieldReporting:\n    owner: A\n"
                f"    data_classification: internal\n    review_date: {date}\n")
    assert rules_of(f) == expect


def test_invalid_classification(tmp_path):
    f = run_tmp(tmp_path, "solutions:\n  NorthbridgeFieldReporting:\n    owner: A\n"
                "    data_classification: secret\n    review_date: 2030-01-01\n")
    assert rules_of(f) == ["PPRC004"]


def test_malformed_manifest_and_rules(tmp_path):
    sol = _copy_compliant(tmp_path)
    bad = tmp_path / "bad.yml"
    bad.write_text("solutions: [unclosed\n", encoding="utf-8")
    f = run_check(str(sol), str(bad), str(ROOT / "rules.yml"), TODAY)
    assert rules_of(f) == ["PPRC103"] and f[0].line
    f = run_check(str(sol), str(tmp_path / "missing.yml"), str(ROOT / "rules.yml"), TODAY)
    assert rules_of(f) == ["PPRC103"]
    badrules = tmp_path / "r.yml"
    badrules.write_text("approved_connectors: nope\n", encoding="utf-8")
    f = run_check(str(sol), str(ROOT / "governance.yml"), str(badrules), TODAY)
    assert rules_of(f) == ["PPRC104"]


def test_flow_with_odd_shapes_does_not_crash(tmp_path):
    sol = _copy_compliant(tmp_path)
    (sol / "Workflows" / "x.json").write_text("[1, 2]", encoding="utf-8")
    (sol / "Workflows" / "y.json").write_text(
        '{"properties": {"connectionReferences": []}}', encoding="utf-8")
    f = run_check(str(sol), str(ROOT / "governance.yml"), str(ROOT / "rules.yml"), TODAY)
    assert rules_of(f) == ["PPRC102", "PPRC102"]


def test_flow_connector_without_api_name_falls_back_to_key(tmp_path):
    sol = _copy_compliant(tmp_path)
    (sol / "Workflows" / "z.json").write_text(
        '{"properties": {"connectionReferences": {"shared_twitter": {}}}}', encoding="utf-8")
    f = run_check(str(sol), str(ROOT / "governance.yml"), str(ROOT / "rules.yml"), TODAY)
    assert rules_of(f) == ["PPRC001"] and "shared_twitter" in f[0].message


def test_github_annotation_format(monkeypatch):
    monkeypatch.chdir(ROOT)
    out = as_github(run_check("samples/noncompliant", "governance.yml", "rules.yml", TODAY))
    first = out.splitlines()[0]
    assert first.startswith(
        "::error file=samples/noncompliant/Other/Customizations.xml,line=30,title=PPRC001")
    assert "\n::error " in out


def test_json_output_is_valid():
    data = json.loads(as_json(check("samples/noncompliant")))
    assert data["ok"] is False and data["count"] == 4
    assert {"rule", "file", "line", "remediation"} <= set(data["findings"][0])


def test_cli_exit_codes(capsys, monkeypatch):
    monkeypatch.chdir(ROOT)
    rest = ["--manifest", "governance.yml", "--rules", "rules.yml", "--today", "2026-11-20"]
    assert main(["check", "samples/compliant", *rest]) == 0
    assert main(["check", "samples/noncompliant", *rest, "--format", "github"]) == 1
    assert main(["check", "samples/malformed", *rest, "--format", "json"]) == 1
    capsys.readouterr()

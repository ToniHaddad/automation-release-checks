import datetime as dt
import json
from pathlib import Path

import pytest

from arc.checks import run_check
from arc.cli import main
from arc.report import as_github, as_json, as_text

ROOT = Path(__file__).resolve().parent.parent
TODAY = dt.date(2026, 11, 22)
RULES = str(ROOT / "rules.yml")
SPREAD = "https://www.googleapis.com/auth/spreadsheets"


def sample(kind):
    base = ROOT / "samples" / kind
    paths = sorted(str(p) for p in (base / "automations").iterdir())
    return paths, str(base / "governance.yml")


def run_sample(kind):
    paths, gov = sample(kind)
    return run_check(paths, gov, RULES, TODAY)


def ids(findings):
    return sorted(f.rule for f in findings)


# ------------------------------------------------------------ the three samples

def test_compliant_set_has_no_findings():
    assert run_sample("compliant") == []


def test_noncompliant_set_hits_every_rule_family():
    f = run_sample("noncompliant")
    assert ids(f) == sorted(["ARC001", "ARC002", "ARC003", "ARC010", "ARC011", "ARC012",
                             "ARC020", "ARC020", "ARC021", "ARC030"])


def test_noncompliant_findings_carry_file_line_and_fix():
    f = run_sample("noncompliant")
    assert all(x.remediation and x.file for x in f)
    by = {(x.rule, x.file.rsplit("/", 1)[-1]): x for x in f}
    assert by[("ARC003", "appsscript.json")].line == 8
    assert by[("ARC021", "Reminders.gs")].line == 13
    assert by[("ARC020", "PurchaseOrders.gs")].line == 16
    assert by[("ARC001", "daily-stock-digest.json")].line is not None
    assert by[("ARC011", "governance.yml")].line == 7


def test_malformed_set_gives_findings_not_a_traceback():
    f = run_sample("malformed")
    assert ids(f) == ["ARC101", "ARC101", "ARC102"]
    assert all(x.line for x in f)


def test_secret_value_is_never_printed():
    f = run_sample("noncompliant")
    for out in (as_text(f), as_json(f), as_github(f)):
        assert "7f3a91c2d4e8b605" not in out


# ------------------------------------------------------------ helpers for small cases

def workflow(nodes, active=True, settings=None, extra=None):
    d = {"name": "WF", "nodes": nodes, "connections": {}, "active": active,
         "settings": settings if settings is not None else {"errorWorkflow": "Err1"}}
    d.update(extra or {})
    return d


def node(ntype, params=None, creds=None, name="N"):
    n = {"id": "1", "name": name, "type": "n8n-nodes-base." + ntype, "typeVersion": 1,
         "position": [0, 0], "parameters": params or {}}
    if creds:
        n["credentials"] = {c: {"id": "1", "name": c} for c in creds}
    return n


@pytest.fixture
def env(tmp_path):
    gov = tmp_path / "gov.yml"

    def write_gov(body=None):
        gov.write_text(body if body is not None else (
            "automations:\n  auto:\n    owner: A role\n    data_classification: internal\n"
            "    review_date: 2035-01-01\n"), encoding="utf-8")

    write_gov()
    folder = tmp_path / "auto"
    folder.mkdir()

    class E:
        pass

    e = E()
    e.folder, e.gov, e.write_gov, e.tmp = folder, gov, write_gov, tmp_path

    def put_wf(wf, name="wf.json"):
        (folder / name).write_text(json.dumps(wf, indent=2), encoding="utf-8")

    def put_script(scopes=(SPREAD,), files=None):
        (folder / "appsscript.json").write_text(
            json.dumps({"timeZone": "Asia/Beirut", "oauthScopes": list(scopes)}, indent=2), encoding="utf-8")
        for k, v in (files or {}).items():
            (folder / k).write_text(v, encoding="utf-8")

    def run(rules=RULES):
        return run_check([str(folder)], str(gov), rules, TODAY)

    e.put_wf, e.put_script, e.run = put_wf, put_script, run
    return e


# ------------------------------------------------------------ allowlist checks

def test_node_type_not_on_allowlist(env):
    env.put_wf(workflow([node("scheduleTrigger"), node("slack", name="Chat")]))
    f = env.run()
    assert ids(f) == ["ARC001"] and "n8n-nodes-base.slack" in f[0].message and f[0].line


def test_approved_node_types_pass(env):
    env.put_wf(workflow([node("scheduleTrigger"), node("supabase", creds=["supabaseApi"]),
                         node("code"), node("emailSend", creds=["smtp"])]))
    assert env.run() == []


def test_credential_type_not_on_allowlist(env):
    env.put_wf(workflow([node("supabase", creds=["supabaseApi", "trelloApi"])]))
    f = env.run()
    assert ids(f) == ["ARC002"] and "trelloApi" in f[0].message


def test_oauth_scope_not_on_allowlist(env):
    env.put_script(scopes=(SPREAD, "https://www.googleapis.com/auth/drive"))
    f = env.run()
    assert ids(f) == ["ARC003"] and f[0].line == 5


def test_same_unapproved_type_in_one_file_reported_once(env):
    env.put_wf(workflow([node("slack", name="a"), node("slack", name="b")]))
    assert ids(env.run()) == ["ARC001"]


# ------------------------------------------------------------ secrets and emails

def test_hardcoded_token_in_gs_file(env):
    env.put_script(files={"Code.gs": 'function f() {\n  const apiToken = "abcd1234efgh5678";\n}\n'})
    f = env.run()
    assert ids(f) == ["ARC020"] and f[0].line == 2 and f[0].file.endswith("Code.gs")


def test_script_property_lookup_is_not_a_secret(env):
    env.put_script(files={"Code.gs": 'const t = PropertiesService.getScriptProperties().getProperty("API_TOKEN");\n'
                                      'const h = {Authorization: "Bearer " + t};\n'})
    assert env.run() == []


def test_js_files_are_scanned_too(env):
    env.put_script(files={"Util.js": 'var password = "hunter2hunter2";\n'})
    assert ids(env.run()) == ["ARC020"]


def test_literal_bearer_token_in_gs(env):
    env.put_script(files={"Code.gs": 'const h = {Authorization: "Bearer abcdef0123456789abcdef"};\n'})
    assert ids(env.run()) == ["ARC020"]


@pytest.mark.parametrize("token", [
    "ghp_" + "a1B2c3D4" * 5,
    "xoxb-" + "1234567890-" * 2 + "abcdefgh",
    "AKIA" + "ABCDEFGHIJKLMNOP",
    "AIza" + "A" * 35,
    "eyJ" + "a" * 12 + "." + "b" * 12 + "." + "c" * 12,
])
def test_known_token_formats(env, token):
    env.put_script(files={"Code.gs": f'const x = "{token}";\n'})
    f = env.run()
    assert ids(f) == ["ARC020"]
    assert token not in f[0].message


def test_private_key_block(env):
    env.put_script(files={"Code.gs": "const k = `-----BEGIN PRIVATE KEY-----\nabc\n`;\n"})
    assert ids(env.run()) == ["ARC020"]


def test_n8n_parameter_with_literal_token(env):
    env.put_wf(workflow([node("supabase", {"accessToken": "tok-1234567890"}, ["supabaseApi"])]))
    f = env.run()
    assert ids(f) == ["ARC020"] and "accessToken" in f[0].message and f[0].line


def test_n8n_expression_and_short_values_are_not_secrets(env):
    env.put_wf(workflow([node("supabase", {"accessToken": "={{ $credentials.token }}",
                                           "apiKey": "", "secret": "abc"}, ["supabaseApi"])]))
    assert env.run() == []


def test_n8n_authorization_header_literal(env):
    params = {"headerParameters": {"parameters": [{"name": "Authorization", "value": "Bearer abcdef0123456789xyz"}]}}
    env.put_wf(workflow([node("code", params)]))
    f = env.run()
    assert ids(f) == ["ARC020"]  # one finding even though two patterns match the same line


def test_secret_inside_code_node_source(env):
    env.put_wf(workflow([node("code", {"jsCode": "const apiKey = 'zzzz-9999-yyyy-8888';\nreturn [];"})]))
    assert ids(env.run()) == ["ARC020"]


def test_literal_personal_email_in_gs(env):
    env.put_script(files={"Code.gs": 'MailApp.sendEmail("someone.else@example.com", "s", "b");\n'})
    f = env.run()
    assert ids(f) == ["ARC021"] and "someone.else@example.com" in f[0].message


def test_allowlisted_role_mailbox_is_fine_but_case_insensitive(env):
    env.put_script(files={"Code.gs": 'MailApp.sendEmail("Supply-Chain@Example.org", "s", "b");\n'})
    assert env.run() == []


def test_literal_email_in_n8n_parameter(env):
    env.put_wf(workflow([node("emailSend", {"toEmail": "a.person@example.net"}, ["smtp"])]))
    assert ids(env.run()) == ["ARC021"]


# ------------------------------------------------------------ error workflow

def test_active_schedule_without_error_workflow(env):
    env.put_wf(workflow([node("scheduleTrigger")], settings={"executionOrder": "v1"}))
    f = env.run()
    assert ids(f) == ["ARC030"] and f[0].line


@pytest.mark.parametrize("wf", [
    workflow([node("scheduleTrigger")], active=False, settings={}),                 # inactive
    workflow([node("manualTrigger")], settings={}),                                 # no schedule
    workflow([node("scheduleTrigger")], settings={"errorWorkflow": "Err1"}),        # has one
])
def test_error_workflow_check_passes(env, wf):
    env.put_wf(wf)
    assert env.run() == []


def test_old_cron_node_counts_as_schedule(env):
    env.put_wf(workflow([node("cron")], settings={}))
    assert "ARC030" in ids(env.run())


def test_blank_error_workflow_counts_as_missing(env):
    env.put_wf(workflow([node("scheduleTrigger")], settings={"errorWorkflow": "  "}))
    assert ids(env.run()) == ["ARC030"]


# ------------------------------------------------------------ governance manifest

def gov_body(owner="A role", cls="internal", review="2035-01-01"):
    lines = ["automations:", "  auto:"]
    if owner is not None:
        lines.append(f"    owner: {owner}")
    if cls is not None:
        lines.append(f"    data_classification: {cls}")
    if review is not None:
        lines.append(f"    review_date: {review}")
    return "\n".join(lines) + "\n"


def test_missing_manifest_entry_means_no_owner(env):
    env.put_script()
    env.write_gov("automations:\n  other:\n    owner: x\n")
    assert ids(env.run()) == ["ARC010"]


def test_blank_owner(env):
    env.put_script()
    env.write_gov(gov_body(owner="'  '"))
    assert ids(env.run()) == ["ARC010"]


def test_missing_owner_key(env):
    env.put_script()
    env.write_gov(gov_body(owner=None))
    f = env.run()
    assert ids(f) == ["ARC010"] and f[0].line == 2


@pytest.mark.parametrize("review,expect", [
    ("2026-11-21", ["ARC011"]),    # yesterday
    ("2026-11-22", []),            # due today is not overdue
    ("2026-11-23", []),
    ('"soon"', ["ARC011"]),
    (None, ["ARC011"]),
])
def test_review_date_boundaries(env, review, expect):
    env.put_script()
    env.write_gov(gov_body(review=review))
    assert ids(env.run()) == expect


@pytest.mark.parametrize("cls,expect", [("secret", ["ARC012"]), (None, ["ARC012"]),
                                        ("Internal", []), ("restricted", [])])
def test_data_classification(env, cls, expect):
    env.put_script()
    env.write_gov(gov_body(cls=cls))
    assert ids(env.run()) == expect


# ------------------------------------------------------------ malformed input

def test_missing_folder(env):
    f = run_check([str(env.tmp / "nope")], str(env.gov), RULES, TODAY)
    assert ids(f) == ["ARC100"]


def test_empty_folder(env):
    assert ids(env.run()) == ["ARC100"]


def test_truncated_workflow_json(env):
    (env.folder / "wf.json").write_text('{"nodes": [{"type": "n8n-nodes-base.code",', encoding="utf-8")
    f = env.run()
    assert ids(f) == ["ARC101"] and f[0].line == 1


def test_json_with_trailing_comma_reports_line(env):
    (env.folder / "wf.json").write_text('{\n  "nodes": [],\n  "active": true,\n}\n', encoding="utf-8")
    f = env.run()
    assert ids(f) == ["ARC101"] and f[0].line == 4


def test_json_that_is_not_a_workflow(env):
    (env.folder / "wf.json").write_text("[1, 2, 3]", encoding="utf-8")
    assert ids(env.run()) == ["ARC102"]


def test_node_without_type(env):
    env.put_wf(workflow([{"name": "x", "parameters": {}}]))
    assert ids(env.run()) == ["ARC102"]


def test_not_utf8_file(env):
    (env.folder / "wf.json").write_bytes(b"\xff\xfe\x00{")
    assert ids(env.run()) == ["ARC101"]


def test_apps_script_manifest_without_scopes(env):
    (env.folder / "appsscript.json").write_text('{"timeZone": "Asia/Beirut"}', encoding="utf-8")
    f = env.run()
    assert ids(f) == ["ARC102"] and "oauthScopes" in f[0].message


def test_apps_script_manifest_not_an_object(env):
    (env.folder / "appsscript.json").write_text("[]", encoding="utf-8")
    assert ids(env.run()) == ["ARC102"]


def test_other_json_beside_appsscript_json_is_ignored(env):
    env.put_script()
    (env.folder / ".clasp.json").write_text('{"scriptId": "x"}', encoding="utf-8")
    (env.folder / "package.json").write_text("{}", encoding="utf-8")
    assert env.run() == []


def test_malformed_manifest_and_rules(env, tmp_path):
    env.put_script()
    env.gov.write_text("automations: [unclosed\n", encoding="utf-8")
    f = env.run()
    assert ids(f) == ["ARC103"] and f[0].line
    f = run_check([str(env.folder)], str(tmp_path / "missing.yml"), RULES, TODAY)
    assert ids(f) == ["ARC103"]
    bad = tmp_path / "r.yml"
    bad.write_text("approved_oauth_scopes: nope\n", encoding="utf-8")
    env.write_gov()
    assert ids(env.run(str(bad))) == ["ARC104"]


def test_rules_file_missing_a_list(env, tmp_path):
    env.put_script()
    bad = tmp_path / "r.yml"
    bad.write_text("approved_oauth_scopes: []\n", encoding="utf-8")
    f = env.run(str(bad))
    assert ids(f) == ["ARC104"] and "approved_n8n_node_types" in f[0].message


# ------------------------------------------------------------ output and CLI

def test_github_annotation_format(monkeypatch):
    monkeypatch.chdir(ROOT)
    paths = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "samples/noncompliant/automations").iterdir())
    f = run_check(paths, "samples/noncompliant/governance.yml", "rules.yml", TODAY)
    out = as_github(f).splitlines()
    scope = next(line for line in out if "ARC003" in line)
    assert scope.startswith(
        "::error file=samples/noncompliant/automations/rental-reminders/appsscript.json,line=8,title=ARC003")
    assert out[-1].startswith("arc: FAILED")


def test_github_annotation_escapes_newlines():
    from arc.models import Finding
    out = as_github([Finding("ARC020", "a\nb, c: d", "fix", "x:y.json", 3)])
    assert "%0A" in out and "file=x%3Ay.json" in out


def test_json_output_is_valid():
    data = json.loads(as_json(run_sample("noncompliant")))
    assert data["ok"] is False and data["count"] == 10
    assert {"rule", "file", "line", "remediation", "title"} <= set(data["findings"][0])


def test_cli_exit_codes_with_several_folders(capsys, monkeypatch):
    monkeypatch.chdir(ROOT)
    for kind, code in (("compliant", 0), ("noncompliant", 1), ("malformed", 1)):
        base = ROOT / "samples" / kind
        dirs = sorted(str(p.relative_to(ROOT)) for p in (base / "automations").iterdir())
        rc = main(["check", *dirs, "--manifest", f"samples/{kind}/governance.yml",
                   "--rules", "rules.yml", "--today", "2026-11-22", "--format", "json"])
        assert rc == code
    capsys.readouterr()

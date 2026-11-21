import json

import pytest

from arc.jsonlines import JSONLineError, parse
from arc.scan import is_placeholder, scan_text, secret_key


def test_parser_agrees_with_json_module():
    text = json.dumps({"a": [1, 2.5, -3e2, True, None, "x\nyé\"q"], "b": {"c": {}}, "d": []}, indent=2)
    value, _ = parse(text)
    assert value == json.loads(text)


def test_parser_records_key_and_item_lines():
    text = '{\n  "nodes": [\n    {"type": "a"},\n    {\n      "type": "b"\n    }\n  ],\n  "active": true\n}\n'
    _, lines = parse(text)
    assert lines[("nodes",)] == 2
    assert lines[("nodes", 0)] == 3
    assert lines[("nodes", 1, "type")] == 5
    assert lines[("active",)] == 8


@pytest.mark.parametrize("text,line", [
    ("", 1), ("{", 1), ('{"a": }', 1), ('{"a": 1,}', 1), ('{\n"a": 1\n"b": 2}', 3),
    ('[1, 2', 1), ('{"a": "unterminated}', 1), ("nul", 1), ('{"a": 1} extra', 1),
    ('{\n\n"a": [1,\n', 3),
])
def test_parser_errors_have_lines(text, line):
    with pytest.raises(JSONLineError) as e:
        parse(text)
    assert e.value.line == line


def test_deeply_nested_input_is_an_error_not_a_crash():
    with pytest.raises(JSONLineError):
        parse("[" * 5000)


def test_scan_masks_the_value():
    hits = scan_text('const apiKey = "abcdefgh12345678";')
    assert len(hits) == 1 and "abcdefgh12345678" not in hits[0].what and hits[0].line == 1


def test_scan_reports_line_numbers():
    hits = scan_text("a\nb\nconst token = 'qwertyuiop1234';\n")
    assert hits[0].line == 3


def test_placeholders_are_ignored():
    for v in ("<your token>", "{{TOKEN}}", "${TOKEN}", "xxxxxxxx", "YOUR_TOKEN_HERE", "changeme"):
        assert is_placeholder(v)
    assert scan_text('const token = "<paste token here>";') == []


def test_secret_key_matches_word_endings_only():
    assert secret_key("accessToken") and secret_key("SLACK_API_KEY") and secret_key("Authorization")
    assert not secret_key("tokenUrl") and not secret_key("secretSheetName")


def test_email_allowlist():
    assert scan_text("to: a@example.org", frozenset({"a@example.org"})) == []
    assert scan_text("to: a@example.org")[0].kind == "email"


def test_literal_basic_auth_header_is_a_secret():
    assert scan_text('{auth: "Basic dXNlcjpwYXNzd29yZDEyMw=="}')[0].kind == "secret"
    assert scan_text('{auth: "Basic " + encoded}') == []

# power-platform-release-checks

`pprc`: a Python CLI and composite GitHub Action that checks an unpacked Power
Platform solution (pac solution unpack layout) for three governance rules:
connector not on the allowlist, no business owner, overdue review. Exit 1 on
any finding. Output: text, json, github annotations.

## Run and test

    python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # Linux: .venv/bin
    pprc check samples/noncompliant --manifest governance.yml --rules rules.yml
    python -m pytest -q
    python scripts/make_terminal_page.py   # regenerates docs/terminal.html + sample-output.txt

## Layout

- `src/pprc/solution.py` parses Solution.xml, Customizations.xml, Workflows/*.json
- `src/pprc/config.py` loads rules.yml and governance.yml (with line numbers)
- `src/pprc/checks.py` the checks; `report.py` output formats; `cli.py` entry
- `rules.yml` organisational rules (approved connectors); `governance.yml` manifest
- `samples/` compliant, noncompliant, malformed solutions (hand-built, not exported)
- `solutions/field-reporting` the repo's own solution, checked on every PR
- `action.yml` composite action; `.github/workflows/` CI and release checks

## Quirks

- Rule ids: PPRC001 connector, 002 owner, 003 review, 004 classification,
  1xx file/config problems. Malformed input must give findings, never a traceback.
- Tests pin `today` to 2026-11-20; sample dates are fixed (2025-01-31 overdue, 2035 future).
- Samples are hand-built to the documented format; no tenant export exists.
- Use `python -m pytest` on Windows (the venv pytest.exe shim may be blocked).

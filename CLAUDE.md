# automation-release-checks

`arc`: a Python CLI and composite GitHub Action that checks n8n workflow exports
and Google Apps Script projects (clasp layout) before release. It blocks: an
n8n node type, n8n credential type or Apps Script OAuth scope that is not on
the allowlist; a hardcoded secret or email address; an active n8n workflow
with a schedule trigger and no error workflow; a missing owner, missing data
classification or overdue review in the governance manifest. Exit 1 on any finding.

## Run and test

    python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # Linux: .venv/bin
    arc check samples/noncompliant/automations/* --manifest samples/noncompliant/governance.yml --rules rules.yml
    python -m pytest -q
    python scripts/make_terminal_page.py   # rewrites docs/terminal.html + sample-output.txt

## Layout

- `src/arc/loaders.py` reads n8n JSON and Apps Script folders into facts and file problems
- `src/arc/jsonlines.py` JSON parser that records the line of every key
- `src/arc/scan.py` secret and email patterns; `checks.py` rules; `report.py` formats; `cli.py`
- `rules.yml` organisational allowlists; `governance.yml` manifest for `automations/`
- `samples/{compliant,noncompliant,malformed}/` three invented automations each, plus a manifest
- `automations/` the repo's own automations, checked on every PR (copy of compliant)
- `action.yml` composite action; `.github/workflows/` CI and release checks

## Quirks

- One folder = one automation; the manifest key is the folder name.
- Rule ids: ARC001-003 allowlists, 010-012 governance, 020 secret, 021 email, 030 error workflow, 1xx file problems.
- Malformed input must give findings, never a traceback. Secret values are masked in output.
- Samples are hand-written to the documented formats, not exported from a live instance. All data is invented.
- Tests pin today to 2026-11-22. Use `python -m pytest` on Windows.
- The repo is public: no real names, addresses, tokens or organisation names. Fake tokens avoid real provider prefixes.

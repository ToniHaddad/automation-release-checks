# automation-release-checks

A command-line tool and GitHub Action that stop an n8n workflow or a Google Apps Script project from being released when it uses a service nobody approved, has no named owner, has an overdue review, or carries a secret or a personal email address in its code.

![arc check on the noncompliant sample set](docs/terminal.png)

## The need

A humanitarian organization in Lebanon runs many small automations: Apps Script projects bound to Google Sheets (rental contract reminders, a menu that pushes purchase orders to the stock system) and n8n workflows on a schedule (a daily stock digest). They are built by one or two people, change often, and move organisational data. The rules for them (which services are allowed, who owns each one, when it was last reviewed, no tokens or personal addresses typed into code) live in a document that nobody opens at release time. `arc` turns those rules into a check that runs on every pull request.

## Try it

```
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"      # Linux/macOS: .venv/bin/pip
.venv/Scripts/arc check samples/noncompliant/automations/* \
    --manifest samples/noncompliant/governance.yml --rules rules.yml
```

It prints the findings and exits 1 (full output in `docs/sample-output.txt`):

```
ARC020  samples/noncompliant/automations/purchase-order-push/PurchaseOrders.gs:16
    Hardcoded secret: 'STOCK_API_TOKEN' is set to a literal value (stk... (25 characters)) in PurchaseOrders.gs.
    Fix: Move it to an n8n credential, or to Script Properties in Apps Script, and rotate it because it is now in the repository history.
ARC010  samples/noncompliant/governance.yml:9
    Automation 'purchase-order-push' has no business owner.
ARC003  samples/noncompliant/automations/rental-reminders/appsscript.json:8
    Apps Script OAuth scope 'https://mail.google.com/' is not on the approved list.
...
FAILED: 10 findings.
```

Options: `--format text|json|github` (`github` prints `::error file=...,line=...,title=...::` annotations),
`--today YYYY-MM-DD`. Several folders can be given at once. The secret itself is never printed, only its first three characters and length.

As an action (see `action.yml`):

```yaml
- uses: actions/checkout@v4
- uses: ToniHaddad/automation-release-checks@main
  with:
    paths: automations/*          # one folder per automation
    manifest: governance.yml
    rules: rules.yml
```

## How it works

One folder is one automation. It holds either exported n8n workflow JSON files, or an Apps Script project as pulled by `clasp` (`appsscript.json` plus `.gs` or `.js` files). The governance manifest is keyed by the folder name.

| Input | What is read |
|---|---|
| n8n workflow `*.json` | each node's `type` and its `credentials` keys; `parameters` (every string, for secrets and emails); `active`; `settings.errorWorkflow` |
| `appsscript.json` | `oauthScopes` |
| `*.gs`, `*.js` | scanned line by line for secrets and email addresses |
| `rules.yml` | `approved_n8n_node_types`, `approved_n8n_credential_types`, `approved_oauth_scopes`, `allowed_email_addresses`, `data_classifications` |
| `governance.yml` | per automation: `owner`, `data_classification`, `review_date` |

| Rule | Meaning |
|---|---|
| ARC001 / 002 | n8n node type / credential type not on the allowlist |
| ARC003 | Apps Script OAuth scope not on the allowlist |
| ARC010 | No business owner (blank, or no manifest entry) |
| ARC011 | Review overdue, missing or not a date. A review due today is not overdue |
| ARC012 | Data classification missing or not an allowed value |
| ARC020 | Hardcoded secret: a literal value under a name ending in token, secret, password, api key or authorization; a literal bearer or basic auth value; a known token format; a private key block |
| ARC021 | Hardcoded email address, unless it is a listed shared role mailbox |
| ARC030 | Active n8n workflow with a schedule trigger and no error workflow |
| ARC100 to 104 | A file or folder is missing, unreadable, not valid JSON or YAML, has an unexpected shape, or the manifest or rules file is broken |

Every finding has the file, the line when it can be known, the rule id and a remediation step. Malformed input produces a finding and a non-zero exit, never a traceback. n8n expressions (values starting with `=`) are not treated as literal secrets. A JSON parser in `src/arc/jsonlines.py` records the line of every key, so node and scope findings point at the exact line.

### What was verified against documentation

- **Apps Script manifest** (Google's manifest reference): `appsscript.json` has `timeZone`, `dependencies`, `exceptionLogging`, `runtimeVersion`, `urlFetchWhitelist`, `webapp`, `addOns` and `oauthScopes`, an array of strings.
- **clasp** (Google's clasp guide): `clasp pull` and `clasp clone` bring a project down to local files in folders, with `.gs` files in the examples. The page does not say whether pulled files are `.gs` or `.js` by default, so `arc` reads both.
- **n8n** (n8n export docs and error handling docs): workflows export as JSON; the export contains credential names and IDs; a workflow's error workflow is chosen in its settings and must start with an Error Trigger node.
- **Not found in official docs, taken from community posts and my own knowledge of the format**: the exact names `nodes`, `connections`, `active`, `settings.errorWorkflow`, node `type` such as `n8n-nodes-base.googleSheets`, `typeVersion`, `credentials` keyed by credential type, and `n8n-nodes-base.scheduleTrigger`. The n8n API reference page I could reach did not document the workflow object. Verify against a real export before relying on a field.

**The samples were hand-written to those formats. They were not exported from a live n8n instance or pulled from a real Apps Script project.** Everything in them is invented, including the mailbox `supply-chain@example.org` (a reserved example domain) and the fake token, which avoids the formats real providers use.

## The samples

Three invented automations, in three sets (`samples/compliant`, `samples/noncompliant`, `samples/malformed`):

- `rental-reminders`: an Apps Script that emails a reminder three months before a rental contract ends or its yearly period ends, plus a weekly recap of overdue items.
- `purchase-order-push`: an Apps Script menu that pushes purchase order rows from a sheet to a stock system, which accepts or rejects each row.
- `stock-digest`: an n8n workflow that sends a daily low-stock and near-expiry digest, with a second workflow that notifies the owner on error.

## Results

Measured by running the tool and the test suite:

- Compliant set: 0 findings, exit 0. Noncompliant set: 10 findings, exit 1 (every rule family appears at least once). Malformed set: 3 findings (two invalid JSON, one `oauthScopes` that is a string), exit 1.
- `python -m pytest -q`: 80 tests pass. They cover each check, the date boundaries (yesterday, today, tomorrow, not a date, missing), each secret pattern, the email allowlist, the error workflow cases, malformed JSON and YAML, missing folders, odd shapes, line numbers, output formats and exit codes.
- Two pull requests show the gate on a repository that starts clean:
  - [PR 3](https://github.com/ToniHaddad/automation-release-checks/pull/3), left open, adds an hourly n8n workflow that posts to a chat service with a token typed into the node. Its "Check automations/" job fails with three annotations:

    ```
    automations/stock-digest/low-stock-chat-alert.json:49 ARC020 Hardcoded secret
      parameter 'accessToken' in node 'Post to chat' in workflow 'Low stock chat alert' holds a literal value (stk... (25 characters))
    automations/stock-digest/low-stock-chat-alert.json:54 ARC001 n8n node type not on the allowlist
      n8n node type 'n8n-nodes-base.slack' (node 'Post to chat' ...) is not on the approved list.
    automations/stock-digest/low-stock-chat-alert.json:61 ARC002 n8n credential type not on the allowlist
      n8n credential type 'slackApi' (node 'Post to chat' ...) is not on the approved list.
    ```
  - [PR 4](https://github.com/ToniHaddad/automation-release-checks/pull/4) sends the alert by email through the approved SMTP credential and the shared mailbox, and passes. It targets PR 3's branch.
- Two earlier pull requests from when the tool targeted another platform were closed unmerged.

## What a static scan cannot see

`arc` reads files in source control. These checks need live information and are outside it:

- **What a credential really holds.** An n8n export has the credential's name and type, not its secret or its permissions. An approved `googleSheetsOAuth2Api` credential could still be a personal account with access to far more than the workflow needs.
- **Who a sheet is shared with.** The Apps Script is bound to a sheet; its sharing, editors and viewers are Drive settings, not code.
- **Whether triggers are installed.** A time-driven Apps Script trigger is created in the editor or by `ScriptApp.newTrigger`, and may exist, be missing or run as someone who left. Whether an n8n workflow is really active on the server is also not in a file that was exported earlier.
- **What the script runs as.** The account that authorised the scopes is only known on the live project.
- **What data actually moves**, how often it runs, and whether runs fail.

## Where it fails

- **Short or oddly named variables are missed.** `const k = "stk-demo-7f3a91c2d4e8b605";` produces no finding, because the name `k` does not end in a secret-like word and the value matches no known token format. Checked by running it.
- **Concatenated secrets are missed.** `"stk-demo-" + "7f3a91c2d4e8b605"` is not seen, for the same reason, and neither is a secret read out of a literal object under an innocent key.
- Apps Script files with no `oauthScopes` in the manifest are reported (ARC102), because Google then infers the scopes at run time; the tool cannot say which they are.
- Any literal address that is not on `allowed_email_addresses` is flagged, including a `mailto:` link in a comment. That is deliberate but noisy.
- Review dates are compared with the clock of the machine running the check; `--today` exists for reruns.

## What I would add next

- Flag outbound hosts: compare `UrlFetchApp.fetch` URLs and n8n HTTP Request URLs with an approved host list.
- Use an entropy check for high-randomness string literals under any variable name, with a reviewed baseline to keep noise down.

## Licence

MIT. Author: Toni Haddad. All data in the samples is invented.

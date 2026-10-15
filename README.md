# GAC Detection Engineering

Standalone detection engineering in VS Code, using Elastic's official
[`detection-rules`](https://github.com/elastic/detection-rules) Python tooling
and GitHub Actions. Rules use native TOML, not a custom JSON schema.

This follows [DaC-Reference](https://github.com/elastic/DaC-Reference) and Elastic's
[custom-rules setup](https://github.com/elastic/detection-rules/blob/main/docs-dev/custom-rules-management.md).
The official repository is a Git submodule at `.elastic/detection-rules`, pinned
at `195f15c0bac84540bfe47abb8e26dbf8184eb69a` (package 3.0.11). It supplies the
rule models, KQL/EQL validation, TOML conversion, packaging and Kibana APIs.
Third-party runtime versions are pinned in `requirements.lock`.

## Getting started: follow this order

1. [Open VS Code and validate locally](#start-in-vs-code).
2. [Create the Elastic automation identity and API key](#create-the-elastic-identity-and-api-key).
3. [Store the key in Bitwarden and create machine tokens](#configure-bitwarden-secrets-manager).
4. [Pull a custom Kibana rule](#pull-rules-created-in-kibana).
5. [Review and push a pull request](#review-and-push-your-first-rule).
6. [Enable GitHub Actions deployment](#github-actions-and-deployment).

Steps 1–5 work without a deployment runner. Step 6 enables writes to Kibana.
This guide covers detection engineering. Entra/Microsoft 365 log collection is
a separate infrastructure task with its own licensing and permissions.

| Item | Purpose | Where to keep it |
| --- | --- | --- |
| Elastic automation password | Recover/sign into the dedicated Elastic identity | Bitwarden Password Manager |
| Encoded Elastic API key | Authorize the tools to Kibana | Bitwarden **Secrets Manager** |
| Bitwarden secret UUID | Identify the stored key; this is not a credential | `ELASTIC_DETECTION_API_KEY_SECRET_ID` |
| Bitwarden machine access token | Allow `bws` to fetch the key | Masked local prompt or GitHub environment secret `BWS_ACCESS_TOKEN` |
| GitHub login | Push branches and open PRs | VS Code/Git Credential Manager sign-in |
| Runner registration token | Enroll the Linux runner once | GitHub runner setup; unrelated to Bitwarden |

Never put credentials into Git, VS Code settings, screenshots or command arguments.
The API key belongs in Secrets Manager, not a Password Manager item that `bws`
cannot read. Bitwarden remains authoritative; GitHub stores only a bootstrap token.

## Start in VS Code

### Already-provisioned management VM125

Connect through Teleport to `win11-mgmt` as `soclab` and open the desktop shortcut
**GAC Detection Engineering**. The prepared repository is
`C:\MyCode\gac-detections`, with Python environment `.venv-elastic`.
In **Terminal → New Terminal**:

```powershell
cd C:\MyCode\gac-detections
git status --short
# Only update main when the working tree is clean; preserve existing edits.
git switch main
git pull --ff-only
git submodule update --init --recursive
$env:CUSTOM_RULES_DIR = (Get-Location).Path
$env:PYTHONUTF8 = '1'
.venv-elastic\Scripts\python.exe -m pip check
.venv-elastic\Scripts\python.exe -m detection_rules validate-all
```

Expected: `No broken requirements found` and `Rule validation successful`.
These local checks need no API key. Press **Ctrl + Shift + B** (hold Ctrl and
Shift, then press B), or use **Terminal → Run Build Task → Elastic: validate rules**.
All tasks use the workspace's Python executable directly. If interpreter selection
is requested, use **Ctrl + Shift + P → Python: Select Interpreter → Enter interpreter
path** and select `C:\MyCode\gac-detections\.venv-elastic\Scripts\python.exe`.

### Fresh workstation instead of VM125

Install Python **3.12**, Git, VS Code and the official
[Bitwarden Secrets Manager CLI (`bws`)](https://bitwarden.com/help/secrets-manager-cli/).
VM125 already has these tools. On a fresh workstation, use PowerShell:

```powershell
git clone --recurse-submodules https://github.com/ccoombes/gac-detections.git
cd gac-detections
# For an existing clone:
git submodule update --init --recursive
py -3.12 -m venv .venv-elastic
.venv-elastic\Scripts\python -m pip install --no-deps -r requirements.txt
.venv-elastic\Scripts\python -m pip check
$env:CUSTOM_RULES_DIR = (Get-Location).Path
$env:PYTHONUTF8 = '1'
code .
```

Use your installed Python 3.12 executable if `py -3.12` is unavailable on Windows.
On Linux, use `python3.12` and `.venv-elastic/bin/python`.
Select `.venv-elastic` as the VS Code interpreter and
install the recommended extensions. Existing users must switch away from the
old Python 3.11 `.venv`; the previous custom `dac` module has been removed.

`--no-deps` is intentional: the requirements include the complete runtime lock
and the three official editable packages from the same pinned submodule. It
prevents upstream floating Git dependency URLs from installing a second revision.
Run `pip check` afterwards. Build-system dependencies are installed through pip's
normal build isolation; the runtime lock is not a byte-for-byte build guarantee.

Ctrl+Shift+B runs **Elastic: validate rules**. VS Code also provides package,
test and authenticated pull tasks; F5 debugs the official validator. Tasks set
`CUSTOM_RULES_DIR` automatically. In a terminal, set it as shown above before
using the native CLI:

```powershell
.venv-elastic\Scripts\python -m detection_rules validate-all
.venv-elastic\Scripts\python -m unittest discover -s tests -v
.venv-elastic\Scripts\python -m detection_rules export-rules-from-repo --directory rules --outfile artifacts/rules.ndjson
```

## Repository layout and authoring

- `_config.yaml`, `etc/`: generated by official `custom-rules setup-config`, targeting stack 9.5 (lab infrastructure specifies 9.5.4).
- `rules/`: custom TOML detections with `[metadata]` and `[rule]` sections.
- `exceptions/`, `action_connectors/`, `actions/`: native dependency collections.
- `.elastic/detection-rules/`: unmodified pinned upstream code; update the submodule in a reviewed PR.
- `scripts/kibana.py`: Bitwarden bootstrap and lab ownership/backup policy around the official CLI.

Create a feature branch. Use native `python -m detection_rules create-rule`
with a destination TOML path, or export a UI-created rule as described below.
Keep `rule_id` stable and the `gac-detections` ownership tag. Set `enabled = false`
until tested. Update metadata dates and increment `[rule].version` on changes.
`bypass_version_lock: true` uses explicit native rule versions rather than the
Elastic prebuilt-release lock strategy. Files have no tactic-name prefix.

Run validation, inspect telemetry/query results in Kibana, and open a PR. The
starter keeps UUID `944cce20-7e5b-43bb-8b08-32e93ee3cb2b` and remains disabled.
Native validation checks query/schema correctness, but does not prove detection
coverage, field availability or successful execution against your live data.

Do not add `--stack-version` to the package command casually: the pinned upstream
CLI's downgrade path generates replacement IDs by default. Packaging without
that flag preserves IDs; an offline integration test enforces this. Rules target
the configured stack through native metadata/config. Revisit compatibility and
identity tests when changing stack or upstream revision.

## Create the Elastic identity and API key

Use the self-managed lab at `https://kibana.gaclab.xyz`, initially in space ID
`default`. A space ID is different from its display name. Retain trusted HTTPS.

### Administrator: initialize detections and create the scoped identity

1. Sign in as your administrator, select the intended space and visit
   **Security → Rules / Detection rules (SIEM)** once to initialize detections.
   The administrator handles bootstrap; do not give the automation account `superuser`.
2. Open **Stack Management → Security → Roles → Create role**. Name the role
   `gac_detection_automation` and configure this starting lab scope:

| Scope | Starting privileges |
| --- | --- |
| Cluster | `manage_own_api_key` for the identity's own key management |
| Source indices | `logs-windows.sysmon_operational-*`: `read`, `view_index_metadata` |
| Detection indices | `.alerts-security.alerts-default`, `.lists-default`, `.items-default`: `manage`, `write`, `read`, `view_index_metadata` |
| Kibana | Selected **Default** space only; **Security: All**, or the version's equivalent Rules/Exceptions and Alerts management features |

3. Leave other applications/spaces ungranted. Add source patterns when rules
   need them. Start without actions; importing actions needs additional connector
   privileges. Follow the installed version's
   [detection privilege requirements](https://www.elastic.co/docs/solutions/security/detect-and-alert/detections-privileges).
4. Open **Stack Management → Security → Users → Create user**. Create
   `svc_gac_detections`, assign only the scoped role and save its recovery
   password in **Bitwarden Password Manager**.

Older upgraded clusters may also require legacy `.siem-signals-<space-id>` access.
The role above can manage rules; it is not an export-only role. Rules also need
source-index access when executing, not just permission to create their definitions.

### Automation identity: create its API key

1. Sign out of the administrator session, or use another browser profile, and
   sign in as `svc_gac_detections`.
2. Search Kibana for **API keys** (also under **Stack Management → Security**).
   Choose **Create API key → User/personal API key** and name it `gac-detections-lab`.
3. Set an expiry, for example 90 days, and record the renewal date. Inherit the
   dedicated user's privileges; do not create an unrestricted administrator key
   or replace its Kibana permissions with an Elasticsearch-only descriptor.
4. Create the key and copy its **encoded/Base64** representation when displayed.
   Store that complete value in the next section, without `ApiKey ` / `Bearer `
   prefixes, JSON quotes or line breaks. The raw `api_key` field or key ID alone
   is not the encoded value. If the one-time value is lost, create a replacement.

This is not a Fleet enrollment token or Elastic Cloud control-plane API key.
[Elastic API-key creation](https://www.elastic.co/docs/deploy-manage/api-keys/elasticsearch-api-keys).

## Configure Bitwarden Secrets Manager

### Store the Elastic key

1. Open the Bitwarden web app, select **Secrets Manager**, and select the lab
   organization. Password Manager items cannot be retrieved by `bws`.
2. Use **New → Project** to create `gac-detections`, dedicated to these credentials.
3. Use **New → Secret**, fill in the following and save:

| Field | Value |
| --- | --- |
| Name | `ELASTIC_DETECTION_DEPLOY_API_KEY` |
| Value | The encoded Elastic API key from the previous section |
| Project | `gac-detections` |
| Notes | Kibana URL, space, owner and expiry date |

4. Record the secret's **UUID/ID**, not its project ID, machine ID or Elastic key
   ID. The terminal example below can discover it by name without printing the
   value if it is not conveniently exposed in the UI.

[Bitwarden secret creation](https://bitwarden.com/help/secrets/).

### Create machine accounts and bootstrap tokens

1. Use **New → Machine account**, naming it `gac-detections-workstation`.
2. Open its **Projects** tab, add `gac-detections` and grant **Can read**. It
   fetches the key; it does not need to edit Bitwarden secrets or access all lab projects.
3. Under **Access tokens → Create access token**, name the token `win11-mgmt`,
   choose an expiry and create it. Save the one-time displayed value securely in
   Bitwarden Password Manager. That token value cannot be retrieved later.
4. For CI, create `gac-detections-ci` with the same project's **Can read** access
   and its own expiring token. If your plan's machine-account quota prevents a
   second account, use separate named tokens on the scoped account so each can
   be revoked separately; document that they share permissions.

Both accounts in this simple setup retrieve the same deployment-capable Elastic
key. Bitwarden **Can read** is not read-only Elastic access. For stronger isolation,
use a separate export-only Elastic key/project for the workstation later.

[Machine accounts](https://bitwarden.com/help/machine-accounts/),
[access tokens](https://bitwarden.com/help/access-tokens/).

## Pull rules created in Kibana

### Create a disabled rule in Kibana

Return to your normal authorized human Kibana account for these authoring steps.

1. Open **Security → Rules → Create new rule** in the intended space. Start
   with a custom query rule using the Sysmon index pattern above and language KQL.
   Test its query against actual events before saving.
2. Supply the name, description, author, schedule/lookback and severity. Add the
   exact tag `gac-detections`. Keep it **disabled** and omit actions/exceptions
   for the first exercise.
3. Copy its **rule_id UUID**, not the saved-object `id` that may appear in the
   browser URL. If the UI does not show it, export the selected rule through
   Kibana and inspect `rule_id` in that NDJSON. Keep raw exports outside Git.

### Export it from the VM125 terminal

Run this in **Terminal → New Terminal**. Paste the machine token only into the
masked prompt; its value does not become part of your PowerShell command history.
The secret UUID is discovered by name without printing its value.

```powershell
cd C:\MyCode\gac-detections
$env:KIBANA_URL = 'https://kibana.gaclab.xyz'
$env:KIBANA_SPACE = 'default'
$env:BWS_BIN = 'C:\Program Files\Bitwarden Secrets Manager\bws.exe'
$env:PYTHONUTF8 = '1'
$ruleId = Read-Host 'Paste the custom rule_id UUID'
$pullDirectory = "artifacts/pulled-$(Get-Date -Format yyyyMMdd-HHmmss)"
$env:BWS_ACCESS_TOKEN = [Net.NetworkCredential]::new(
    '', (Read-Host 'Bitwarden workstation machine token' -AsSecureString)
).Password

try {
    # Capture JSON in memory; never print raw secret responses.
    $items = @(& $env:BWS_BIN secret list | ConvertFrom-Json)
    if ($LASTEXITCODE) { throw 'Bitwarden lookup failed' }
    $matches = @($items | Where-Object key -eq 'ELASTIC_DETECTION_DEPLOY_API_KEY')
    if ($matches.Count -ne 1) { throw 'Expected one matching secret in the machine account scope' }
    $env:ELASTIC_DETECTION_API_KEY_SECRET_ID = $matches[0].id
    Remove-Variable items,matches
    Write-Host "Bitwarden secret UUID: $env:ELASTIC_DETECTION_API_KEY_SECRET_ID"

    .venv-elastic\Scripts\python.exe scripts/kibana.py pull --rule-id $ruleId --directory $pullDirectory
    if ($LASTEXITCODE) { throw 'Rule export failed; see troubleshooting below' }
    Write-Host "Review exported files in $pullDirectory"
} finally {
    Remove-Item Env:BWS_ACCESS_TOKEN -ErrorAction SilentlyContinue
    Remove-Variable items,matches -ErrorAction SilentlyContinue
}
```

Expected: `Elastic exported 1 rule(s) ...; review before moving into rules/`.
Kibana is unchanged. The token is cleared after the block. The secret UUID remains
in `ELASTIC_DETECTION_API_KEY_SECRET_ID` for copying into GitHub configuration.

The VS Code **Elastic: pull rule from Kibana** task needs these variables in the
VS Code process environment. Setting them only in an already-open terminal does
not configure other editor tasks. Use the terminal block for your first export.

The helper invokes native `detection_rules kibana export-rules`, including native
exception and connector exports. Its default destination is ignored
`artifacts/pulled/`; the example uses a new timestamped folder.
Use `--directory artifacts/pulled-next` for another export; a nonempty destination
is refused. Kibana is unchanged. Inspect the files in VS Code, then move the
reviewed rule into `rules/` and dependency files into their corresponding root
collections. Reconcile by stable ID to avoid duplicate local copies. Increase
the version for reviewed changes, validate, commit on a feature branch and open
a PR. Connector credentials are not supplied by exporting definitions; keep them
in Bitwarden and provision separately. Never commit sensitive connector config.

The official CLI is also available directly with `CUSTOM_RULES_DIR` set:
`python -m detection_rules kibana export-rules --help`. It supports selection by
ID, name or query. Consult the pinned upstream `CLI.md` for options. This project
does not automatically synchronize UI edits or push exported files to Git.

## Review and push your first rule

1. Create a branch: `git switch -c detections/my-first-rule`.
2. Open the export folder in VS Code Explorer and review its TOML files. Search
   the existing `rules/` collection for the same `rule_id`. Reconcile the existing
   file when present; never add duplicate IDs.
3. For a new rule, create `rules/imported/` and move the reviewed rule TOML there.
   Review dependency files before moving them into root `exceptions/` and
   `action_connectors/`. Never commit sensitive connector configuration.
4. Preserve ID, ownership tag and disabled state. Update metadata dates and
   increment `[rule].version` above the existing/exported version for changes.
5. Run **Elastic: validate rules**, **Elastic: test** and **Elastic: package rules**.
   Inspect the packaged query/ID/enabled state and test query behavior in Kibana.
6. Commit only the reviewed files and push:

```powershell
git diff
# Replace with the specific TOML path you reviewed:
git add "rules/imported/your-reviewed-rule.toml"
git commit -m "Add first custom detection"
git push -u origin HEAD
```

If Git asks for identity, use `git config user.name "Your Name"` and
`git config user.email "your-github-email"` for this repository. Follow Git
Credential Manager's browser sign-in when prompted; do not put a token into
the remote URL. On GitHub, choose the branch's **Compare & pull request**, inspect
**Validate rules**, then merge after review. With deployment disabled, this only
validates and packages; it does not change Kibana.

## GitHub Actions and deployment

### Configure the environment and enable the first deployment

The repository is currently public. Before attaching a runner with lab access,
choose the private/trusted repository or isolated ephemeral runner design in
the [runner setup guide](docs/github-actions.md). VM125 remains a workstation.

1. In GitHub, open **Settings → Environments → New environment** and name it
   exactly `elastic-security-lab`.
2. Under **Deployment branches and tags**, allow only branch `main`, not tags.
   Add a reviewer if desired. Feature availability depends on visibility/plan;
   keep deployment disabled if you cannot enforce the required protection.
3. Add the following **environment secret** and **environment variables**:

| Name | Kind | Value |
| --- | --- | --- |
| `BWS_ACCESS_TOKEN` | Environment secret | CI machine token from Bitwarden; do not reuse the workstation token |
| `ELASTIC_DETECTION_API_KEY_SECRET_ID` | Environment variable | Secret UUID discovered above; not the encoded key |
| `KIBANA_URL` | Environment variable | `https://kibana.gaclab.xyz` |
| `KIBANA_SPACE` | Environment variable | `default` |

4. In **Settings → Secrets and variables → Actions → Variables**, create
   **repository variable** `DETECTION_DEPLOY_ENABLED` with value `false` initially.
   This must be repository-scoped: the job condition runs before environment
   variables become available.
5. Protect `main` with PR review and required status check **Validate rules**.
   Review workflow, script, dependency and submodule changes too.
6. Complete the Linux runner steps in the linked guide. Confirm Online/Idle,
   labels `self-hosted`, `linux`, `gac-detections`, and trusted private Kibana access.
7. Set repository variable `DETECTION_DEPLOY_ENABLED` to literal `true`.
   Choose **Actions → Detection engineering → Run workflow → main → Run workflow**.
   A subsequent reviewed merge to main also triggers deployment.
8. Inspect **Validate rules**, **Deploy rules** and `detection-package`. Existing
   rule definitions are backed up as `rules-before-deployment`; entirely new
   rules have no previous definitions to back up.
9. In Kibana, verify IDs/versions and that the starter remains disabled. Enable
   tested rules through a reviewed Git change, then inspect execution and alerts.

[GitHub environments and protection](https://docs.github.com/en/actions/concepts/workflows-and-actions/deployment-environments).

Follow [GitHub Actions setup](docs/github-actions.md). Pull requests/main validate
on hosted Ubuntu using Python 3.12 and the official CLI, then publish a same-run
package. Main deploys through the official `kibana import-rules --overwrite` on
an internal Linux runner only after `DETECTION_DEPLOY_ENABLED=true` is configured.
The wrapper supplies Bitwarden credentials in-process, preflights every target,
backs up existing definitions via native export and rejects incomplete import
responses. It contains no replacement rule schema, query parser or HTTP client.

Deployment refuses prebuilt/unowned collisions, decreasing versions and changes
to existing action/exception references that have not been reconciled. Dependency
objects use native import behavior; existing connector/exception definitions are
not automatically overwritten. Manage dependency changes in a separate reviewed
operation. Only deploy trusted code on the private runner.

API imports are not atomic. On failure inspect Kibana, then retry the reviewed
commit or restore native backup TOMLs through a version-increased Git commit.
Never delete a rule by removing its file; retire it with `enabled = false`.
UI edits to Git-managed rules may be overwritten on the next deployment.

Offline tests exercise the actual official parser, packaging and API-to-TOML
conversion, plus the lab deployment guards. Authenticated local export needs the
scoped credentials above; CI deployment also needs the runner and protected
environment. These instructions do not provision credentials or perform a live import.

## Credential rotation and recovery

- **Elastic key:** create a replacement as the scoped identity, update the
  Bitwarden secret value in place (keeping its UUID), verify authenticated
  export/deployment, then invalidate the old key. Record expiration dates.
- **Bitwarden token:** create a replacement from the correct machine account,
  update its GitHub environment secret or securely stored workstation token,
  verify access, then revoke the old token.
- **Permissions:** revise the Elastic role, refresh the API key as required and
  redeploy reviewed rules to refresh execution authorization. Do not assume
  every existing rule's authorization snapshot updates automatically.
- **Bad deployment:** inspect partial successes before retrying. Restore native
  backup TOMLs through a reviewed, version-increased Git commit. Retire a bad
  new rule with `enabled = false`; removing its file never deletes the remote rule.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Wrong build-task path | Open `gac-detections.code-workspace`, update clean main, then reopen. Windows tasks must resolve to `C:\MyCode\gac-detections\.venv-elastic\Scripts\python.exe`. |
| `No module named detection_rules` | Use `.venv-elastic`, initialize the submodule and install requirements from the repo root. The old `.venv` / custom `dac` module is obsolete. |
| `bws` not found | Set `BWS_BIN` to the executable shown above. Linux service accounts need the binary on their service PATH. |
| Bitwarden lookup fails | Check token expiry, organization/region, project assignment, read permission and exact secret name/UUID. `bws` is different from the Password Manager `bw` CLI. |
| `ValueError` during setup | Check secret ID and rule ID are UUIDs, not names or another type of ID. |
| HTTP 401 / authentication failure | Store the encoded Elastic key without a header prefix; confirm it and the Bitwarden token have not expired. |
| HTTP 403 / preflight denied | Check selected space, Elastic role/Kibana features and index privileges. Bitwarden read permission does not grant Elastic access. |
| DNS/TLS/connection error | Check private DNS/NPM mapping, routing and the trusted certificate chain. Do not bypass certificate verification. |
| Nonempty pull directory | Use a new `--directory artifacts/pulled-<name>`; preserve previous exports. |
| Duplicate ID / unmanaged collision | Reconcile the existing file or opt a custom UI rule into ownership with the tag. Do not reuse a prebuilt Elastic rule's ID. |
| Actions/exceptions differ | Review native dependency files and reconcile deliberately; the guard prevents silently removing references. |
| Deploy skipped | Confirm the repository variable is literal `true`, the ref is main and the run is not a PR. |
| Deploy queued | Check runner labels/availability, protected environment and pending approvals. |
| Imported rule produces no alerts | Check enabled state, execution errors, source privileges/mappings, lookback, ingestion and matching test events. |

Authenticated errors suppress raw API responses. Inspect Kibana audit/server
logs through authorized administration instead of printing tokens or raw secret
objects. For Bitwarden EU/self-hosted deployments, configure the official CLI's
matching endpoint using its vendor documentation.

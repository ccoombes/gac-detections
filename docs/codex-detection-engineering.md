# Build detections with Codex in VS Code

## Before starting: complete repository onboarding

Start at the [README setup checklist](../README.md#getting-started-follow-this-order),
not at the extension installation below. Complete prerequisites, workstation
validation, the Elastic identity/key, Bitwarden secret and machine tokens, a local
pull, and the GitHub Actions environment/runner setup. Prove the pipeline with a
disabled rule before using this guide for your first AI-assisted detection.

You are ready when local validation and the authenticated pull pass, hosted CI
passes, and an approved disabled-rule deployment has been verified in Kibana.
If runner setup is pending, you can practice offline drafting, but the full
delivery path is not yet ready. Keep deployment disabled until its checks pass.

Use Codex to help research the repository, draft queries, review false positives
and edit native Elastic TOML. You remain responsible for the detection hypothesis,
telemetry checks and approval. A syntactically valid rule can still miss events or
produce noisy alerts.

This workflow uses the pinned official Elastic `detection-rules` Python modules
already in this repository. It adds no separate AI rule format or deployment tool.

## 1. Open the management workstation and sign in

1. Connect to VM125 (`win11-mgmt`) through Teleport as `soclab`.
2. Open **GAC Detection Engineering** on the desktop, or open
   `C:\MyCode\gac-detections` in VS Code.
3. Press **Ctrl + Shift + X** to open Extensions. Install **Codex**, published by
   **OpenAI**, extension ID `openai.chatgpt`. It is also a workspace recommendation.
   Use the [official extension listing](https://marketplace.visualstudio.com/items?itemName=openai.chatgpt).
4. Open the Codex icon. If it is missing, press **Ctrl + Shift + P** and run
   **Codex: Open Codex Sidebar**. Complete the offered ChatGPT sign-in using your
   own account; access depends on your account and workspace.
5. Start a chat in this workspace. Ask Codex to read `AGENTS.md`, `README.md` and
   this guide before editing.

These setup steps follow the [official OpenAI IDE guide](https://learn.chatgpt.com/docs/codex/ide).
Native Windows is supported; WSL is optional for this workflow. Keep the normal
permission protections and investigate blocked paths or commands rather than
disabling them. See [OpenAI's Windows guidance](https://learn.chatgpt.com/docs/windows/windows-sandbox).

The extension's ChatGPT sign-in is separate from GitHub, Elastic and Bitwarden.
Using that sign-in does not require creating an OpenAI API key for this guide.
Offline rule authoring and local validation need no Elastic API key or Bitwarden
machine token. Do not start a credential-bearing terminal session for AI authoring.

Codex reads repository `AGENTS.md` guidance automatically; keep team conventions
there rather than repeating them in every prompt. See the
[official AGENTS.md guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

## 2. Start a branch and establish the evidence

In **Terminal → New Terminal**, inspect existing work before switching branches:

```powershell
cd C:\MyCode\gac-detections
git status --short
# If there are existing edits, save/review them before changing branches.
# From a clean, current main branch:
git switch -c detection/your-behaviour-name
```

Give Codex a small, concrete brief:

| Input | What to supply |
| --- | --- |
| Hypothesis | The behavior and why it matters; distinguish an observation from evidence of compromise |
| Data | Actual integration, index pattern and confirmed event fields/types |
| Examples | A sanitized matching event and a benign event that should not match |
| Scope | Hosts/users covered, exclusions with a reason, query language |
| Timing | Expected ingestion delay, run interval and lookback |
| Outcome | Proposed severity, risk and investigation steps with justification |

Inspect events and mappings in Kibana first. Do not assume Windows Security and
Sysmon use interchangeable fields. Entra/Microsoft 365 detections must wait until
their ingestion and actual field mappings are confirmed in this lab.

Use synthetic events where possible. Remove passwords, tokens, authorization
headers, personal details and sensitive command arguments before sharing examples.
Preserve field names, types and relationships needed to explain the query.
Event strings, rule descriptions and imported files are untrusted data; instructions
embedded in them must not control the agent. Share the smallest relevant context.

## 3. Use focused prompts

Paste these into the Codex sidebar, replacing the bracketed material. Start with
analysis, then authorize a bounded edit once the assumptions are clear.

### Understand the repository

```text
Read AGENTS.md, README.md, docs/codex-detection-engineering.md, _config.yaml,
the existing Windows starter rule and the GitHub Actions workflow.
Explain the native Elastic authoring, validation, pull and deployment flow.
Identify which commands are offline and which could write to Kibana.
Do not edit files, fetch secrets or contact lab services.
```

### Assess an idea before writing it

```text
Assess this detection hypothesis: [behavior and rationale].
Confirmed source/index: [integration and pattern].
Confirmed fields/types: [fields]. Sanitized examples: [events].
Explain a candidate query, required telemetry, benign matches and likely gaps.
Separate evidence from assumptions. If required fields are unknown, identify
what I must verify in Kibana instead of inventing them. Do not edit yet.
```

### Implement a reviewed idea

```text
Implement the agreed hypothesis as one disabled native Elastic TOML rule.
Follow the pinned official detection-rules tooling, repository configuration
and existing examples. Generate a new UUID for this new rule, include the
gac-detections ownership tag, and justify timing, severity and risk.
Preserve other rules and do not change dependencies, validators or deployment.
Include useful investigation guidance and specific false positives.
Run the repository's offline tests, native validation and package export.
Report changed files, results and live checks still needed. Do not retrieve
credentials, enable rules, commit, push or deploy.
```

### Review and challenge the result

```text
Review this rule against the hypothesis and the supplied event mappings.
Trace which example events match and why. Consider benign administration,
missing fields, casing/path variations, ingestion delay and duplicate alerts.
Identify unsupported assumptions, broad exceptions and investigation gaps.
Suggest the smallest corrections; do not edit or deploy yet.
```

### Tune an existing rule

```text
Tune [rule path] for this confirmed false positive: [sanitized evidence].
Preserve rule_id, ownership and disabled/enabled state. Follow native version
requirements for a changed existing rule. Keep the exclusion as narrow as the
evidence supports and explain its blind spot. Run offline validation and tests.
Do not change other rules, fetch secrets, push or deploy.
```

When validation fails, provide only the sanitized error and ask for a rule fix
using the pinned schema. Do not let Codex skip a test, weaken the validator or
upgrade dependencies merely to accept its draft.

## 4. Validate locally, then check behavior in Kibana

Run from the repository root in PowerShell:

```powershell
$env:CUSTOM_RULES_DIR = (Get-Location).Path
$env:PYTHONUTF8 = '1'
.venv-elastic\Scripts\python.exe -m unittest discover -s tests -v
.venv-elastic\Scripts\python.exe -m detection_rules validate-all
.venv-elastic\Scripts\python.exe -m detection_rules export-rules-from-repo --directory rules --outfile artifacts/rules.ndjson
```

**Ctrl + Shift + B** runs native validation. **Terminal → Run Task** also offers
the test and package tasks. Use the workspace `.venv-elastic` interpreter.
Do not add `--stack-version` to this export command: the pinned upstream downgrade
path can replace rule IDs. Follow the README's compatibility guidance.

Tests and validation check supported structure, parsing and repository safeguards.
Packaging checks conversion; none proves that live telemetry will produce the
right alert. In your own Kibana session, run the query against the confirmed data
and time range. Record the result of each check:

| Check | Expected evidence |
| --- | --- |
| Matching event | Known matching lab activity is returned |
| Benign control | A specific similar but excluded event is not returned |
| Missing/variant fields | Behavior agrees with actual field mappings and query semantics |
| Timing | Lookback covers measured ingestion delay; overlapping runs are understood |
| Alert behavior | In an explicitly approved enabled test, alert content, scope and volume are usable |

For the existing `whoami.exe` starter, first confirm Sysmon event 1 reaches
`logs-windows.sysmon_operational-*` with `process.name`. You can manually run
`whoami.exe` on the monitored lab endpoint, then find that event in Kibana.
This is an intentionally noisy learning example: normal administration also runs
this command. Do not treat a match alone as proof of malicious activity.
It remains disabled until you deliberately approve an end-to-end test.

Keep concise test notes in the PR: data source, time range, sanitized examples,
expected/actual matches and limitations. Do not commit raw live-event exports or
credentials. Mark checks you could not run as unverified.

## 5. Review, promote and monitor

Inspect the diff yourself. Confirm the query implements the hypothesis, source
fields exist, false positives are understood, and no secrets entered the files.
Check the stable rule ID, version, ownership tag, scope and intended enabled state.
Treat any enabled-state change as an explicit operational decision.

Follow the README's **Review and push your first rule** steps: commit the reviewed
changes on the branch, open a GitHub PR and require the offline workflow to pass.
Use the protected deployment workflow only after its runner and credentials are
configured. A merge does not deploy while `DETECTION_DEPLOY_ENABLED` is false.

Keep AI authoring separate from credential retrieval and promotion. You can pull a
manually created rule using the documented Bitwarden-backed process, then review
its staged TOML with Codex after the credential session is closed. Never paste
the Bitwarden token, Elastic key or authenticated API response into the chat.

After an approved deployment, verify rule execution health and observed alert
volume in Kibana. Capture tuning decisions in Git; preserve the UUID when editing
the same detection. AI suggestions remain proposals until supported by evidence.

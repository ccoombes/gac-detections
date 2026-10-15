# GAC Detection Engineering

A standalone, VS Code-based repository for custom Elastic Security rules.
Azure Pipelines validates PRs, packages rules, and deploys the validated main
commit to the lab's private Kibana endpoint.

```text
VS Code → feature branch → PR validation → merge main → Azure Pipelines → Kibana
                                                        ↓
                                               Bitwarden API-key lookup
```

This follows Elastic's [DaC-Reference direct API workflow](https://github.com/elastic/DaC-Reference/blob/main/docs/core_component_syncing_rules_and_data_from_vcs_to_elastic_security.md):
Git-authoritative rules, validation, CI/CD, stable IDs and pre-deployment backups.
Reference reviewed at commit `a587b771cb7db4900f2a613623998336eeb13f49`.
It is a small implementation of that documented option, rather than a fork of
Elastic's much larger detection-rules framework.

## Start in VS Code

Python 3.11+ is required. From this repository in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.lock
code .
```

Select the `.venv` Python interpreter and install the recommended extensions.
Use **Terminal → Run Task → DaC: validate rules**, or press Ctrl+Shift+B.
The Test Explorer runs the unit tests; F5 debugs validation. JSON completion and
validation apply automatically to `rules/**/*.json`.

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python -m dac validate
.venv\Scripts\python -m dac build
```

## Authoring workflow

1. Create a feature branch and one JSON file per detection under `rules/`.
2. Assign a new UUID `rule_id` once; retain it for every later revision.
3. Keep the `gac-detections` ownership tag. Increment `version` when changing behavior.
4. Validate locally and test the query against representative lab telemetry in Kibana.
5. Open a PR, review the diff and merge into protected `main`.
6. The pipeline creates/updates only the rules in the validated artifact.

The starter `discovery_whoami.json` is intentionally disabled and uses Windows
Sysmon events. Confirm mappings and false positives before enabling it in Git.
Initial support is custom KQL query and EQL rules. The schema intentionally
rejects other rule types, connectors, exceptions and arbitrary server metadata;
extend schema, tests and deployment dependency handling together when needed.
ES|QL, exception-list synchronization and actions can be added later.

Local validation checks JSON/schema, IDs, ownership and the supported rule
contract. It does **not** parse KQL/EQL, verify field mappings, simulate detection
behavior, check licensing, or guarantee a rule will execute. Kibana validates
the API request; validate query logic and inspect rule execution after deployment.

## Pipeline setup

Follow [Azure DevOps setup](docs/azure-devops.md). The YAML has two stages:

| Stage | Runner | Credentials | Runs |
| --- | --- | --- | --- |
| Validate | Microsoft-hosted Ubuntu | None | PRs and main |
| Deploy | Private Linux agent in `GAC-SOC-Lab` | Bitwarden bootstrap token | Main only |

PR triggers in YAML work for GitHub. Azure Repos needs a branch build-validation
policy. Enforce main-only access on the deployment pool, variable group and
environment outside YAML so a PR cannot bypass the condition by editing it.
The Azure organization/project, remote repository, pipeline and agent still
need to be connected; nothing has been published or deployed from this scaffold.

## Credentials and local plan

Bitwarden Secrets Manager holds the **encoded Elastic API key**, in a dedicated
machine secret. The CLI retrieves it using its secret UUID. Keep the bootstrap
`BWS_ACCESS_TOKEN` in an Azure secret variable scoped to the deployment job.
Do not put the Elastic API key, credentials files or tokens in the repository.
Local use requires an existing authorized Bitwarden machine token in the process
environment and the official `bws` CLI on PATH:

```powershell
$env:KIBANA_URL = 'https://kibana.gaclab.xyz'
$env:KIBANA_SPACE = 'default'
$env:ELASTIC_DETECTION_API_KEY_SECRET_ID = '<Bitwarden secret UUID>'
.venv\Scripts\python -m dac deploy           # read-only preflight + backup
.venv\Scripts\python -m dac deploy --apply   # explicit local write
```

Trusted HTTPS is mandatory; redirects and certificate bypass are refused.
The key's privileges determine detection execution rights. Use a dedicated
automation identity, scoped Kibana detection-management rights and read access
to required source indices. Follow [Elastic's privilege guidance](https://www.elastic.co/docs/solutions/security/detect-and-alert/detection-engine-overview)
for the installed version; initialize the detection engine once as an administrator.
Do not give the deployment key `superuser` or use the human `elastic` account.

## Updates, retirement and recovery

All target IDs are preflighted before the first write. Existing prebuilt rules,
unowned IDs, or rules with unmanaged actions/exceptions cause a refusal.
Definitions before an update are saved in the private pipeline artifact
`rules-before-deployment`; API keys and server metadata are excluded. Configure
artifact retention for the desired recovery period.

API writes are **not atomic** across multiple rules. A failure stops the job;
previously written rules may remain changed. Fix the problem and rerun the same
commit, or restore definitions via a reviewed Git commit with increased versions.
For a bad newly created rule, commit `enabled: false`. Missing Git files are
never interpreted as deletion requests. Retire a rule by disabling it in Git and
keeping its stable ID/history. UI edits to owned rules are overwritten on deploy.

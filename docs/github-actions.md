# Connect GitHub Actions

The workflow is `.github/workflows/detections.yml`. Pull requests and main
commits validate on GitHub-hosted Ubuntu. Deployment is initially disabled;
enable it after completing the setup below. No Azure DevOps account is needed.

## 1. Protect main and the deployment environment

Require pull requests and the `Validate rules` status check on main. Review
workflow, schema, deployment code and rule changes before merging.
Create environment `elastic-security-lab` under Settings → Environments and
restrict deployment branches to the selected branch `main` (no tags).
Environment protection availability depends on repository visibility and plan.
Keep deployment disabled if these restrictions cannot be enforced.

Use a private repository for a persistent runner with lab connectivity. PR
validation belongs on GitHub-hosted runners. A YAML condition and runner label
are routing controls, not isolation: modified workflows can request a runner.
Restrict collaborators who can modify workflows; do not attach a persistent
lab runner to a public repository accepting untrusted contributions. For that
model, first provide isolated ephemeral runners with restricted network access.

## 2. Lab deployment runner

Register a repository-scoped Linux GitHub Actions runner with custom label
`gac-detections`, using Settings → Actions → Runners. Run it as a dedicated
unprivileged service account. Provisioning belongs in the infrastructure repo;
VM105 is a possible host. Install Python 3.11+, venv support, Git and a pinned
official Bitwarden `bws` release with verified publisher checksum. Avoid root
and container socket access. Keep the runner updated.

The runner needs outbound GitHub Actions, PyPI and Bitwarden access, and trusted
HTTPS to `https://kibana.gaclab.xyz`. Verify private DNS from its service account;
the lab may need an internal override to NPM at `192.168.10.105`. Manage that
through infrastructure code. No public Kibana exposure or interactive Teleport
session is required.

## 3. Bitwarden credentials and GitHub configuration

Create a dedicated Elastic automation identity/API key with detection-management
and source-index privileges for the intended space. Store the **encoded** key
in Bitwarden Secrets Manager as `ELASTIC_DETECTION_DEPLOY_API_KEY`. Give a
dedicated Bitwarden machine account read-only access to that secret/project.

In the `elastic-security-lab` GitHub environment, configure:

| Name | Kind | Value |
| --- | --- | --- |
| `BWS_ACCESS_TOKEN` | Environment secret | Scoped Bitwarden machine token |
| `ELASTIC_DETECTION_API_KEY_SECRET_ID` | Environment variable | API-key secret UUID |
| `KIBANA_URL` | Environment variable | `https://kibana.gaclab.xyz` |
| `KIBANA_SPACE` | Environment variable | `default` or space ID |

Keep Bitwarden authoritative; GitHub stores only the bootstrap token. Never
enable shell tracing or store credentials in VS Code settings. Finally set the
**repository variable** `DETECTION_DEPLOY_ENABLED` to `true`. This opt-in avoids
queuing deployment jobs before the private runner and environment are ready.

## 4. First deployment and recovery

Inspect the successful validation run and disabled starter rule artifact. After
setup, run `Detection engineering` manually on main or merge a reviewed change.
Deploy consumes the artifact from the same run and backs up previous definitions
as `rules-before-deployment`. Artifacts are accessible to repository readers;
backups omit credentials, but rule queries may contain operational details.
Retention is 14 days for packages and 30 days for backups.

Concurrency prevents overlapping deployments and never cancels an active write.
GitHub may replace older pending runs with newer ones; rules represent complete
desired state, so intermediate revisions need not all deploy. API writes are
not atomic. Inspect failures and rerun or restore with a version-bumped commit.
Confirm the starter remains disabled, then test telemetry before enabling it.

References: [Elastic DaC reference](https://github.com/elastic/DaC-Reference),
[GitHub deployment controls](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments),
[self-hosted runners](https://docs.github.com/en/actions/concepts/runners/self-hosted-runners).

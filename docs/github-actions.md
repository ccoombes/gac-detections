# Connect GitHub Actions

The workflow is `.github/workflows/detections.yml`. It installs the pinned official
Elastic submodule packages with `pip install --no-deps -r requirements.txt`. Pull requests and main
commits validate on GitHub-hosted Ubuntu. Deployment is initially disabled;
enable it after completing the setup below. No Azure DevOps account is needed.

This is step 6 of the [README onboarding checklist](../README.md#getting-started-follow-this-order).
First complete the workstation, Elastic API key, Bitwarden project/machine-token
setup and successful local pull there. Run hosted validation with deployment
disabled before adding the protected environment and runner below. After a
successful disabled-rule deployment, continue to the README's Codex authoring
and PR workflow. Keep credentials and runner installation here separate from
the Codex chat.

## 1. Protect main and the deployment environment

Require pull requests and the `Validate rules` status check on main. Review
workflow, native configuration, deployment code and rule changes before merging.
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
VM105 is a possible host. Install Python 3.12, venv support, Git (including the pinned submodule) and a pinned
official Bitwarden `bws` release with verified publisher checksum. Avoid root
and container socket access. Keep the runner updated.

The runner needs outbound GitHub Actions, PyPI and Bitwarden access, and trusted
HTTPS to `https://kibana.gaclab.xyz`. Verify private DNS from its service account;
the lab may need an internal override to NPM at `192.168.10.105`. Manage that
through infrastructure code. No public Kibana exposure or interactive Teleport
session is required.

### 2a. Prepare a Linux service account and Python

These persistent-runner steps assume you have chosen the private/trusted
repository model in section 1. For the current public repository, stop before
runner registration unless an isolated ephemeral runner design is in place.
Use the infrastructure repo's Terraform/Ansible to provision/rebuild the host;
the commands below describe the required configuration, not a new VM deployment.

On a Rocky Linux 9.4+ host, from your administrative shell:

```bash
sudo dnf install -y git curl unzip python3.12 python3.12-pip
sudo useradd --create-home --shell /bin/bash gac-actions
sudo install -d -o gac-actions -g gac-actions /opt/gac-actions-runner
python3.12 --version
```

For Ubuntu 24.04 instead, install `git curl unzip python3.12 python3.12-venv`
with `apt`, then create the same account/directory. Do not add the account to
sudoers or container-runtime groups. Skip account creation if it already exists.
[RHEL Python package guidance](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/installing_and_using_dynamic_programming_languages/assembly_installing-and-using-python_installing-and-using-dynamic-programming-languages).

### 2b. Install a verified Bitwarden CLI on the runner

This example pins the same official `bws` 2.1.0 release used by VM125, for Linux
x86_64 GNU. Review a version/checksum change together before updating it:

```bash
bws_stage="$(mktemp -d)"
cd "$bws_stage"
curl --fail --location --output bws.zip \
  https://github.com/bitwarden/sdk-sm/releases/download/bws-v2.1.0/bws-x86_64-unknown-linux-gnu-2.1.0.zip
printf '%s  %s\n' \
  'ba8233c3a4aee5d43e3c73bbd04d99e9bc5aba13bbbfd06d89b073abe732b860' \
  bws.zip | sha256sum --check -
unzip bws.zip -d unpacked
sudo install -m 0755 unpacked/bws /usr/local/bin/bws
bws --version
```

The checksum must pass before installation. It comes from the publisher's
[release checksum file](https://github.com/bitwarden/sdk-sm/releases/download/bws-v2.1.0/bws-sha256-checksums-2.1.0.txt).
Do not persist a Bitwarden token in the runner's shell profile: the workflow
injects its scoped environment secret only into the deployment step.

### 2c. Register and start the GitHub runner

1. On GitHub, open **Settings → Actions → Runners → New self-hosted runner**.
   Select **Linux / x64**. Use the current download, SHA256 verification and
   extraction commands shown there; runner versions change independently of
   this repository. Record the selected release/checksum in infrastructure code.
2. Enter the runner account and directory, then perform those download/verify/
   extract commands as this account, not root:

```bash
sudo -iu gac-actions
cd /opt/gac-actions-runner
# Run GitHub's download, checksum verification and extraction commands here.
exit
```

3. If the runner requires native system dependencies, the administrator can run
   the verified runner's `bin/installdependencies.sh`. Then register interactively:

```bash
sudo -iu gac-actions
cd /opt/gac-actions-runner
./config.sh
```

At the prompts, supply repository URL `https://github.com/ccoombes/gac-detections`,
the temporary registration token from GitHub, runner name `gac-detections-lab`,
additional label `gac-detections`, and the default work folder. Default labels
include self-hosted/Linux/X64; the workflow requests Linux and `gac-detections`.
The registration token is not the Bitwarden token or a stored Elastic key.
Interactive registration keeps it out of shell history. Exit to the administrator
shell after successful configuration.

4. Install the service as the dedicated user and start it:

```bash
cd /opt/gac-actions-runner
sudo ./svc.sh install gac-actions
sudo ./svc.sh start
sudo ./svc.sh status
```

5. Confirm the runner is **Idle/Online** on GitHub. Check connectivity and
   executables as the service account:

```bash
sudo -iu gac-actions
command -v git python3.12 bws
getent ahostsv4 kibana.gaclab.xyz
curl --silent --show-error --output /dev/null --write-out '%{http_code}\n' \
  https://kibana.gaclab.xyz/api/status
exit
```

TLS verification must succeed; an HTTP 200 or authentication-required 401 can
confirm the endpoint responds. DNS/TLS failures need infrastructure correction,
not `curl -k`. Confirm the address is the internal proxy, not a public exposure.
An interactive `command -v` check alone does not prove systemd has the same PATH;
the workflow's `command -v bws` and first deployment verify the service context.

[GitHub runner registration](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners),
[service configuration](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/configure-the-application).

## 3. Bitwarden credentials and GitHub configuration

Follow the [README's complete Elastic/Bitwarden setup](../README.md#create-the-elastic-identity-and-api-key)
first. It covers the role, user, encoded key, secret/project, machine accounts,
token handling and first local pull. The settings below are the CI counterpart.

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

Inspect the successful native validation run and disabled starter TOML/NDJSON artifact. After
setup, run `Detection engineering` manually on main or merge a reviewed change.
Deploy consumes the artifact from the same run and backs up previous definitions
as `rules-before-deployment`. Artifacts are accessible to repository readers;
native TOML backups omit execution API keys, but rules and connector metadata
may contain operational details.
Retention is 14 days for packages and 30 days for backups.

Concurrency prevents overlapping deployments and never cancels an active write.
GitHub may replace older pending runs with newer ones; rules represent complete
desired state, so intermediate revisions need not all deploy. API writes are
not atomic. Inspect failures and rerun or restore with a version-bumped commit.
Confirm the starter remains disabled, then test telemetry before enabling it.
Deployment calls `scripts/kibana.py deploy`, which bootstraps Bitwarden and invokes
the official `kibana export-rules` / `kibana import-rules` commands. It fails the
job if the native import response contains errors or missing successful rules.
Existing action/exception-reference changes need separate dependency review;
the workflow does not enable native overwrite-exceptions/overwrite-connectors.

References: [Elastic DaC reference](https://github.com/elastic/DaC-Reference),
[GitHub deployment controls](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments),
[self-hosted runners](https://docs.github.com/en/actions/concepts/runners/self-hosted-runners).

# Connect Azure DevOps

## 1. Repository and pipeline

Push this standalone Git repository to GitHub or Azure Repos. Create an Azure
pipeline in the chosen organization/project using `/azure-pipelines.yml`.
For GitHub, authorize only this repository through the Azure Pipelines GitHub
App. For Azure Repos, add a required automatic build-validation policy on main;
YAML `pr` triggers do not apply. Protect main against direct pushes and require
review of pipeline code, schema, deployment code and rule changes.

## 2. Private deployment agent

Create the Linux pool `GAC-SOC-Lab`. Run the official Azure Pipelines agent as a
dedicated, unprivileged service account on a lab Linux server (VM105 is a possible
host; provisioning belongs in the infrastructure repository). Install Python
3.11+, venv support, Git, and a pinned official Bitwarden `bws` CLI release.
Verify the CLI's publisher release checksum during provisioning. Avoid running
the agent as root or granting Podman/Docker socket access.

The agent needs outbound Azure DevOps, package-index and Bitwarden connectivity,
and trusted HTTPS access to `https://kibana.gaclab.xyz` on the private network.
Check DNS from the agent account; current lab service names may require an
internal override to NPM at `192.168.10.105`. Keep that configuration in the
infrastructure repository. Do not expose Kibana publicly or rely on an
interactive Teleport login for unattended deployment. PR validation uses hosted
agents; do not run untrusted PR code on the private deployment agent.

## 3. Bitwarden and Elastic

Create an Elastic automation identity/key with appropriate detection-management
and source-index privileges for the lab space. Store its **encoded** API key
in Bitwarden Secrets Manager, e.g. `ELASTIC_DETECTION_DEPLOY_API_KEY`.
Create a Bitwarden machine account with read-only access to that secret/project.
Keep its access token as a bootstrap secret, never in YAML, command arguments or
VS Code settings. Azure job logs must not enable shell tracing (`set -x`).

Create variable group `gac-detections-deploy`:

| Variable | Value | Secret? |
| --- | --- | --- |
| `BWS_ACCESS_TOKEN` | Bitwarden machine access token | Yes |
| `ELASTIC_DETECTION_API_KEY_SECRET_ID` | UUID of the encoded API-key secret | No |
| `KIBANA_URL` | `https://kibana.gaclab.xyz` | No |
| `KIBANA_SPACE` | `default` or a dedicated space ID | No |

Authorize only this pipeline to use the group. Never use an organization-wide
or human Bitwarden token. Provision the actual credential through Bitwarden;
no example credential is included here.

## 4. Enforce deployment boundaries outside YAML

Create environment `elastic-security-lab`. Configure resource **Branch control**
checks allowing only `refs/heads/main`, requiring branch protection, on the
deployment environment, private pool and secret variable group. Restrict resource
administration and pipeline edit rights. These checks are required because a PR
can modify its YAML conditions; a condition alone is not a credential boundary.
An environment approval can be added if desired, but is not required by this
simple main-branch workflow. Use an exclusive deployment lock with sequential
behavior on the environment to avoid overlapping rule updates from separate runs.

## 5. First run

Run Validate first. Inspect the disabled starter rule artifact. Then merge a
reviewed main commit and inspect Deploy: preflight plan, backup artifact and
Kibana rule entry. The starter remains disabled until explicitly changed in Git.
Inspect rule execution status after enabling and generate known test telemetry.
This repository has local tests; an actual Azure run and live deployment cannot
be verified until the organization, project, agent and credentials are configured.

References: [Elastic DaC reference](https://github.com/elastic/DaC-Reference),
[Azure Repos PR validation](https://learn.microsoft.com/en-us/azure/devops/pipelines/repos/azure-repos-git),
[resource checks](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/approvals),
[rule authentication](https://www.elastic.co/docs/api/doc/kibana/operation/operation-createrule).

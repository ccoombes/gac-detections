# GAC Detection Engineering

This standalone repository owns custom Elastic Security detections only.
Use Python 3.12, VS Code, native TOML and GitHub Actions. Follow README.md.
Elastic's official detection-rules tooling is pinned as a Git submodule.
Do not reintroduce a custom rule schema, parser or deployment API implementation.
Use CUSTOM_RULES_DIR pointing to this repository with native CLI commands.
Bitwarden Secrets Manager is authoritative for machine credentials. Never
commit secrets, raw API responses or certificate material. Require trusted HTTPS.
Keep rule_id stable and the gac-detections ownership tag. Preserve disabled state.
Never delete automatically; retire with enabled=false in Git.
Run python -m unittest discover -s tests and python -m detection_rules validate-all
before committing. Native validation does not prove live detection effectiveness.
Review submodule/runtime-lock updates together. Deploy only through the protected
main-branch workflow or an explicit request. Keep infrastructure in the lab repo.

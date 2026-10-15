# GAC Detection Engineering

This standalone repository owns custom Elastic Security detections only.
Use Python 3.11+, VS Code, JSON rules and Azure Pipelines. Follow README.md.
Bitwarden Secrets Manager is authoritative for machine credentials. Never
commit secrets, API responses containing credentials, or certificate material.
Require trusted HTTPS. Do not disable TLS checks or expose Kibana publicly.
Keep rule_id stable. Only rules tagged gac-detections may be overwritten.
Never delete rules automatically; retire with enabled=false in Git.
Run python -m unittest discover -s tests and python -m dac validate before committing.
Validation checks structure and policy; it does not prove query correctness.
Deploy only through the documented main-branch pipeline or an explicit request.

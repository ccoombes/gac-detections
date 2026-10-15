"""Bitwarden bootstrap and lab deployment policy around Elastic's official CLI.

Rule parsing, validation, conversion, export and import belong to detection_rules.
This file contains no replacement rule schema or HTTP client.
"""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
OWNER = "gac-detections"


class PolicyError(Exception):
    pass


def configure():
    url = os.environ.get("KIBANA_URL", "")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise PolicyError("Set KIBANA_URL to a trusted HTTPS base URL.")
    secret_id = os.environ.get("ELASTIC_DETECTION_API_KEY_SECRET_ID", "")
    UUID(secret_id)
    if not os.environ.get("BWS_ACCESS_TOKEN"):
        raise PolicyError("Set BWS_ACCESS_TOKEN in the process environment.")
    result = subprocess.run([os.environ.get("BWS_BIN", "bws"), "secret", "get", secret_id],
                            capture_output=True, text=True, check=True, timeout=30)
    key = json.loads(result.stdout)["value"]
    if not isinstance(key, str) or not key or any(c in key for c in "\r\n"):
        raise PolicyError("Invalid Bitwarden API-key value.")
    os.environ["CUSTOM_RULES_DIR"] = str(ROOT)
    os.environ["DR_KIBANA_URL"] = url
    os.environ["DR_API_KEY"] = key
    os.environ["DR_IGNORE_SSL_ERRORS"] = "false"
    return url, key, os.environ.get("KIBANA_SPACE", "default")


def native(args):
    from detection_rules.main import root
    # Never echo raw authenticated responses or tracebacks into CI logs.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return root(args=args, standalone_mode=False)


def check_import(result, expected):
    response, imported = result
    if (response.get("errors") or response.get("success") is not True
            or response.get("success_count") != len(expected)
            or {r.get("rule_id") for r in imported if r.get("rule_id")} != set(expected)):
        raise PolicyError("Elastic import reported incomplete success. Inspect Kibana before retrying.")


def preflight(client, rules):
    existing = []
    for rule in rules:
        if OWNER not in rule.get("tags", []):
            raise PolicyError("Every deployed rule requires the gac-detections ownership tag.")
        response = client.get("/api/detection_engine/rules", params={"rule_id": rule["rule_id"]},
                              raw=True, error=False, verbose=False, timeout=45, allow_redirects=False)
        if response.status_code == 404:
            continue
        if response.status_code != 200:
            raise PolicyError("Kibana preflight failed; no deployment started.")
        old = response.json()
        if old.get("rule_id") != rule["rule_id"] or old.get("immutable") or OWNER not in old.get("tags", []):
            raise PolicyError("Refusing an unmanaged or prebuilt rule collision.")
        if rule.get("version", 1) < old.get("version", 1):
            raise PolicyError("Local version would decrease; increase it before deploying.")
        for field in ("actions", "exceptions_list"):
            if old.get(field, []) != rule.get(field, []):
                raise PolicyError("Action/exception dependencies differ; reconcile them before deploying.")
        existing.append(rule["rule_id"])
    return existing


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["pull", "deploy"])
    parser.add_argument("--rule-id", action="append", default=[])
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--backup", type=Path, default=ROOT / "artifacts/backups")
    args = parser.parse_args(argv)
    try:
        if args.command == "pull" and not args.rule_id:
            raise PolicyError("Select at least one rule_id UUID.")
        for rule_id in args.rule_id:
            UUID(rule_id)
        url, key, space = configure()
        prefix = ["kibana", "--space", space]
        if args.command == "pull":
            target = args.directory or ROOT / "artifacts/pulled"
            if target.exists() and any(target.iterdir()):
                raise PolicyError("Use a new or empty pull directory to protect existing work.")
            options = ["export-rules", "--directory", str(target), "--default-author", "GAC SOC Lab",
                       "--export-exceptions", "--exceptions-directory", str(target / "exceptions"),
                       "--export-action-connectors", "--action-connectors-directory", str(target / "action_connectors")]
            for rule_id in args.rule_id:
                options += ["--rule-id", rule_id]
            exported = native(prefix + options)
            if {r.id for r in exported} != set(args.rule_id):
                raise PolicyError("Not all selected rules exported; inspect the staging directory.")
            print(f"Elastic exported {len(exported)} rule(s) to {target}; review before moving into rules/.")
        else:
            if args.rule_id:
                raise PolicyError("Deploy uses the validated directory, not --rule-id.")
            from detection_rules.rule_loader import RuleCollection
            from kibana import Kibana
            directory = args.directory or ROOT / "rules"
            collection = RuleCollection()
            collection.load_directories([directory])
            rules = [r.contents.to_api_format() for r in collection]
            if not rules:
                raise PolicyError("Empty deployment refused.")
            client = Kibana(kibana_url=url, api_key=key, space=space, verify=True)
            with client:
                existing = preflight(client, rules)
            if existing:
                options = ["export-rules", "--directory", str(args.backup),
                           "--export-exceptions", "--exceptions-directory", str(args.backup / "exceptions"),
                           "--export-action-connectors", "--action-connectors-directory", str(args.backup / "action_connectors")]
                for rule_id in existing:
                    options += ["--rule-id", rule_id]
                backed_up = native(prefix + options)
                if {r.id for r in backed_up} != set(existing):
                    raise PolicyError("Backup incomplete; deployment refused.")
            result = native(prefix + ["import-rules", "--directory", str(directory), "--overwrite"])
            check_import(result, [r["rule_id"] for r in rules])
            print(f"Elastic imported {len(rules)} rule(s).")
        return 0
    except Exception as exc:
        # Upstream exceptions can include response bodies; print only safe policy messages.
        message = str(exc) if isinstance(exc, PolicyError) else type(exc).__name__
        print(f"ERROR: {message}; authenticated response details withheld.", file=sys.stderr)
        return 1
    finally:
        os.environ.pop("DR_API_KEY", None)


if __name__ == "__main__":
    raise SystemExit(main())

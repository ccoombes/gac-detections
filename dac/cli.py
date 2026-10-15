"""Validate, package and upsert repository-owned detection rules. No automatic deletion."""
import argparse
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, HTTPSHandler

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
OWNER = "gac-detections"


class DacError(Exception):
    pass


def load_rules(directory=ROOT / "rules"):
    schema = json.loads((ROOT / "schemas/rule.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    result, seen = [], set()
    for path in sorted(Path(directory).rglob("*.json")):
        try:
            rule = json.loads(path.read_text(encoding="utf-8"))
            errors = sorted(validator.iter_errors(rule), key=lambda e: str(e.path))
            if errors:
                raise DacError(f"{path.name}: {errors[0].message}")
        except (ValueError, OSError) as exc:
            raise DacError(f"Cannot parse rule: {path.name}") from exc
        if rule["rule_id"] in seen:
            raise DacError(f"Duplicate rule_id: {rule['rule_id']}")
        seen.add(rule["rule_id"])
        result.append(rule)
    if not result:
        raise DacError("No JSON rules found; refusing an empty deployment.")
    return result


def package(rules, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(rule, sort_keys=True) + "\n" for rule in rules), encoding="utf-8")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DacError("HTTP redirect refused; use the direct trusted Kibana URL.")


class Kibana:
    def __init__(self, url, key, space="default"):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise DacError("KIBANA_URL must be a trusted HTTPS base URL without credentials/query/fragment.")
        if not key or any(c in key for c in "\r\n"):
            raise DacError("Missing or invalid API key.")
        prefix = "" if space == "default" else "/s/" + quote(space, safe="")
        self.base = url.rstrip("/") + prefix + "/api/detection_engine/rules"
        self.key = key
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))

    def request(self, method, suffix="", body=None, missing_ok=False):
        request = Request(self.base + suffix, method=method,
                          data=None if body is None else json.dumps(body).encode(),
                          headers={"Authorization": "ApiKey " + self.key, "kbn-xsrf": OWNER, "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=45) as response:
                return json.load(response)
        except HTTPError as exc:
            if missing_ok and exc.code == 404:
                return None
            # Do not print API response bodies or credentials.
            raise DacError(f"Kibana {method} failed: HTTP {exc.code}; inspect Kibana audit/server logs.") from None
        except (URLError, ValueError, TimeoutError, OSError):
            raise DacError("Kibana connection/TLS/JSON failure; check the direct URL, DNS, trust and agent network.") from None


def bitwarden_key():
    secret_id = os.environ.get("ELASTIC_DETECTION_API_KEY_SECRET_ID", "")
    if not secret_id or not os.environ.get("BWS_ACCESS_TOKEN"):
        raise DacError("Set BWS_ACCESS_TOKEN and ELASTIC_DETECTION_API_KEY_SECRET_ID.")
    try:
        completed = subprocess.run([os.environ.get("BWS_BIN", "bws"), "secret", "get", secret_id],
                                   check=True, capture_output=True, text=True, timeout=30)
        key = json.loads(completed.stdout)["value"]
        if not isinstance(key, str) or not key:
            raise ValueError()
        return key
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        raise DacError("Bitwarden secret lookup failed; no credential or CLI response has been logged.") from None


def sync(client, rules, backup, apply=False):
    """Read and check every target before the first write; each rule update is independent."""
    previous, plan = [], []
    allowed = set(json.loads((ROOT / "schemas/rule.schema.json").read_text())["properties"])
    for rule in rules:
        old = client.request("GET", "?" + urlencode({"rule_id": rule["rule_id"]}), missing_ok=True)
        if old is not None:
            if not isinstance(old, dict) or old.get('rule_id') != rule['rule_id']:
                raise DacError('Unexpected preflight response; refusing all writes.')
            if old.get("immutable") or OWNER not in old.get("tags", []):
                raise DacError(f"Refusing unmanaged/prebuilt collision: {rule['rule_id']}")
            if old.get("actions") or old.get("exceptions_list"):
                raise DacError("Actions/exceptions exist on a target; migrate those dependencies before overwriting.")
            if rule["version"] < old.get("version", 1):
                raise DacError("Rule version would decrease; bump version for a rollback commit.")
            if any(old.get(k) != v for k, v in rule.items()) and rule['version'] <= old.get('version', 1):
                raise DacError('Changed rule requires an increased version.')
            previous.append({k: v for k, v in old.items() if k in allowed})
        plan.append({"rule_id": rule["rule_id"], "operation": "update" if old else "create"})
    # Backups contain rule definitions only, never execution API keys or server metadata.
    package(previous, backup)
    print(json.dumps({"apply": apply, "rules": plan}, indent=2))
    if apply:
        for rule, item in zip(rules, plan):
            method = "PUT" if item["operation"] == "update" else "POST"
            response = client.request(method, body=rule)
            if not isinstance(response, dict) or response.get("rule_id") != rule["rule_id"] or response.get("error"):
                raise DacError("Unexpected deployment response; stop and inspect the target before retrying.")


def pull(client, rule_ids, directory, overwrite=False):
    """Pull explicitly selected, UI-opted-in rules without changing Kibana."""
    schema = json.loads((ROOT / "schemas/rule.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    # Only discard known response metadata and documented empty/default options.
    metadata = {"id", "created_at", "created_by", "updated_at", "updated_by",
                "revision", "immutable", "rule_source", "execution_summary",
                "api_key", "api_key_owner", "api_key_created_by_user", "output_index",
                "updated_by_user"}
    defaults = {"actions": [], "exceptions_list": [], "filters": [], "threat": [],
                "risk_score_mapping": [], "severity_mapping": [], "to": "now",
                "meta": {}, "throttle": "no_actions", "building_block_type": None,
                "timestamp_override": None, "timestamp_override_fallback_disabled": False,
                "event_category_override": None, "tiebreaker_field": None,
                "timeline_id": None, "timeline_title": None, "license": "",
                "rule_name_override": None, "data_view_id": None, "namespace": "default",
                "related_integrations": [], "required_fields": [], "setup": ""}
    directory = Path(directory)
    existing = load_rules(directory) if any(directory.rglob("*.json")) else []
    local = {rule["rule_id"]: rule for rule in existing}
    prepared = []
    for rule_id in dict.fromkeys(rule_ids):
        # Validate IDs before using them in filenames.
        if not FormatChecker().conforms(rule_id, "uuid"):
            raise DacError("--rule-id must be a UUID.")
        old = client.request("GET", "?" + urlencode({"rule_id": rule_id}))
        if not isinstance(old, dict) or old.get("rule_id") != rule_id:
            raise DacError("Unexpected pull response.")
        if old.get("immutable") or OWNER not in old.get("tags", []):
            raise DacError("Select a custom rule and add the gac-detections tag in Kibana before pulling.")
        unsupported = [k for k, v in old.items() if k not in schema["properties"]
                       and k not in metadata and not (k in defaults and v == defaults[k])]
        if unsupported:
            raise DacError("Unsupported rule fields; nothing written: " + ", ".join(sorted(unsupported)))
        rule = {k: v for k, v in old.items() if k in schema["properties"]}
        if rule_id in local and not overwrite:
            raise DacError("Rule already exists locally; review Git changes or use --overwrite explicitly.")
        # A reviewed import is a new Git revision, including when replacing local code.
        rule["version"] = max(rule.get("version", 1), local.get(rule_id, {}).get("version", 1)) + 1
        errors = list(validator.iter_errors(rule))
        if errors:
            raise DacError("Pulled rule does not meet the repository schema; nothing written: " + errors[0].message)
        paths = [p for p in directory.rglob("*.json")
                 if json.loads(p.read_text(encoding="utf-8")).get("rule_id") == rule_id]
        target = paths[0] if paths else directory / "imported" / (rule_id + ".json")
        prepared.append((target, rule))
    # All selected rules must pass before any local file is replaced.
    for target, rule in prepared:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(prepared)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "build", "deploy", "pull"])
    parser.add_argument("--rule-id", action="append", help="Kibana rule_id UUID to pull; repeat to select multiple.")
    parser.add_argument("--overwrite", action="store_true", help="Explicitly replace existing local rules during pull.")
    parser.add_argument("--rules", type=Path, default=ROOT / "rules")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/rules.ndjson")
    parser.add_argument("--backup", type=Path, default=ROOT / "artifacts/backups/before.ndjson")
    parser.add_argument("--apply", action="store_true", help="Write rules; deploy without this flag is read-only.")
    args = parser.parse_args(argv)
    try:
        if args.command == "pull":
            if not args.rule_id:
                raise DacError("pull requires at least one --rule-id; no bulk import is implicit.")
            client = Kibana(os.environ.get("KIBANA_URL", ""), bitwarden_key(), os.environ.get("KIBANA_SPACE", "default"))
            count = pull(client, args.rule_id, args.rules, args.overwrite)
            print(f"pull: {count} rule(s) saved for Git review; Kibana unchanged.")
            return 0
        rules = load_rules(args.rules)
        if args.command == "build":
            package(rules, args.output)
        elif args.command == "deploy":
            client = Kibana(os.environ.get("KIBANA_URL", ""), bitwarden_key(), os.environ.get("KIBANA_SPACE", "default"))
            sync(client, rules, args.backup, args.apply)
        print(f"{args.command}: {len(rules)} rule(s) passed.")
        return 0
    except DacError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

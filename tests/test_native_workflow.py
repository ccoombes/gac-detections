"""Exercise the pinned official tooling and the small lab policy adapter offline."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
os.environ["CUSTOM_RULES_DIR"] = str(ROOT)

from detection_rules.main import root
from detection_rules.rule import TOMLRule, TOMLRuleContents
from detection_rules.rule_loader import RuleCollection
from kql.errors import KqlParseError
from scripts.kibana import PolicyError, check_import, preflight


class NativeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.rule = RuleCollection().load_file(ROOT / "rules/windows/gac_whoami_process_discovery_starter.toml")
        self.payload = self.rule.contents.to_api_format()

    def test_native_validate_and_package_preserve_identity_and_disabled_state(self):
        output = Path(self.temp.name) / "rules.ndjson"
        with contextlib.redirect_stdout(io.StringIO()):
            root(args=["validate-all"], standalone_mode=False)
            root(args=["export-rules-from-repo", "--directory", str(ROOT / "rules"), "--outfile", str(output)], standalone_mode=False)
        exported = json.loads(output.read_text())
        self.assertEqual(exported["rule_id"], "944cce20-7e5b-43bb-8b08-32e93ee3cb2b")
        self.assertIs(exported["enabled"], False)
        self.assertEqual(exported["query"], self.payload["query"])

    def test_native_parser_rejects_invalid_kql(self):
        data = self.rule.contents.to_dict()
        data["rule"]["query"] = 'process.name: ("whoami.exe"'
        with self.assertRaises(KqlParseError):
            TOMLRuleContents.from_dict(data)

    def test_native_api_to_toml_round_trip_preserves_ui_filters_and_omits_api_key(self):
        resource = dict(self.payload, related_integrations=[], api_key="never-save-this",
                        filters=[{"query": {"match_phrase": {"host.name": "lab-endpoint"}}}])
        contents = TOMLRuleContents.from_rule_resource(resource)
        path = Path(self.temp.name) / "pulled.toml"
        TOMLRule(contents=contents, path=path).save_toml()
        restored = RuleCollection().load_file(path).contents.to_api_format()
        self.assertEqual(restored["rule_id"], self.payload["rule_id"])
        self.assertEqual(restored["filters"], resource["filters"])
        self.assertNotIn("never-save-this", path.read_text())

    def test_policy_refuses_unmanaged_collision_before_import(self):
        client = Mock()
        response = client.get.return_value
        response.status_code = 200
        response.json.return_value = dict(self.payload, tags=["other"])
        with self.assertRaisesRegex(PolicyError, "unmanaged"):
            preflight(client, [self.payload])
        client.post.assert_not_called()

    def test_policy_allows_new_rules_and_collects_existing_backup_ids(self):
        client = Mock()
        missing, found = Mock(status_code=404), Mock(status_code=200)
        found.json.return_value = self.payload
        client.get.side_effect = [missing, found]
        self.assertEqual(preflight(client, [self.payload, self.payload]), [self.payload["rule_id"]])
        client.post.assert_not_called()

    def test_native_import_partial_failure_cannot_report_success(self):
        with self.assertRaises(PolicyError):
            check_import(({"success": False, "success_count": 0, "errors": [{}]}, []), [self.rule.id])
        with self.assertRaises(PolicyError):
            check_import(({"success": True, "success_count": 1, "errors": []}, []), [self.rule.id])
        check_import(({"success": True, "success_count": 1, "errors": []}, [self.payload]), [self.rule.id])


if __name__ == "__main__":
    unittest.main()

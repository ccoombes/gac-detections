import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from dac.cli import DacError, Kibana, NoRedirect, ROOT, load_rules, sync


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.rules = load_rules()[:1]
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.backup = Path(self.temp.name) / "before.ndjson"

    def test_schema_rejects_duplicate_id(self):
        for name in ("a", "b"):
            (Path(self.temp.name) / f"{name}.json").write_text(json.dumps(self.rules[0]))
        with self.assertRaisesRegex(DacError, "Duplicate"):
            load_rules(self.temp.name)

    def test_rejects_action_connector_or_server_secret_in_rule(self):
        for field in ("actions", "api_key", "exceptions_list"):
            rule = copy.deepcopy(self.rules[0])
            rule[field] = []
            path = Path(self.temp.name) / "bad.json"
            path.write_text(json.dumps(rule))
            with self.assertRaises(DacError):
                load_rules(self.temp.name)

    def test_preflight_checks_all_targets_before_any_write(self):
        client = Mock()
        second = dict(self.rules[0], rule_id="f0209bda-99cb-418c-8dd7-c267404b2f39")
        client.request.side_effect = [None, dict(second, tags=["other-owner"])]
        with self.assertRaisesRegex(DacError, "collision"):
            sync(client, self.rules + [second], self.backup, apply=True)
        self.assertEqual([c.args[0] for c in client.request.call_args_list], ["GET", "GET"])

    def test_plan_never_writes(self):
        client = Mock()
        client.request.return_value = None
        sync(client, self.rules, self.backup)
        self.assertEqual(client.request.call_count, 1)

    def test_backup_strips_execution_credentials(self):
        client = Mock()
        old = dict(self.rules[0], api_key="must-not-be-saved", id="server-id")
        client.request.return_value = old
        sync(client, self.rules, self.backup)
        text = self.backup.read_text()
        self.assertNotIn("must-not-be-saved", text)
        self.assertNotIn("server-id", text)
        self.assertEqual(json.loads(text)["rule_id"], old["rule_id"])

    def test_apply_updates_owned_and_creates_missing(self):
        for old, expected in [(None, "POST"), (self.rules[0], "PUT")]:
            with self.subTest(expected=expected):
                client = Mock()
                client.request.side_effect = [old, self.rules[0]]
                sync(client, self.rules, self.backup, apply=True)
                self.assertEqual(client.request.call_args.args[0], expected)

    def test_partial_failure_stops_instead_of_reporting_success(self):
        client = Mock()
        second = dict(self.rules[0], rule_id="f0209bda-99cb-418c-8dd7-c267404b2f39")
        client.request.side_effect = [None, None, {"error": "server error"}]
        with self.assertRaises(DacError):
            sync(client, self.rules + [second], self.backup, apply=True)
        self.assertEqual(client.request.call_count, 3)

    def test_changed_rule_requires_version_bump_before_writes(self):
        client = Mock()
        client.request.return_value = dict(self.rules[0], enabled=True)
        with self.assertRaisesRegex(DacError, "increased version"):
            sync(client, self.rules, self.backup, apply=True)
        self.assertEqual(client.request.call_count, 1)

    def test_unmanaged_dependencies_are_not_silently_removed(self):
        client = Mock()
        client.request.return_value = dict(self.rules[0], actions=[{"id": "connector"}])
        with self.assertRaisesRegex(DacError, "dependencies"):
            sync(client, self.rules, self.backup, apply=True)
        self.assertEqual(client.request.call_count, 1)

    def test_refuses_insecure_url_and_redirect(self):
        with self.assertRaises(DacError):
            Kibana("http://kibana.example", "secret")
        with self.assertRaises(DacError):
            NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example")


if __name__ == "__main__":
    unittest.main()

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from dac.cli import DacError, Kibana, NoRedirect, ROOT, load_rules, sync, pull


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

    def test_pull_preserves_identity_strips_credentials_and_only_reads_kibana(self):
        client = Mock()
        client.request.return_value = dict(self.rules[0], api_key="secret-value", id="server-id", filters=[], to="now")
        self.assertEqual(pull(client, [self.rules[0]["rule_id"]], self.temp.name), 1)
        imported = load_rules(self.temp.name)[0]
        self.assertEqual(imported["rule_id"], self.rules[0]["rule_id"])
        self.assertEqual(imported["version"], self.rules[0]["version"] + 1)
        self.assertNotIn("secret-value", next(Path(self.temp.name).rglob("*.json")).read_text())
        self.assertEqual(client.request.call_args.args[0], "GET")

    def test_pull_checks_all_selected_rules_before_writing(self):
        client = Mock()
        second = dict(self.rules[0], rule_id="f0209bda-99cb-418c-8dd7-c267404b2f39", filters=[{"term": {"host.name": "test"}}])
        client.request.side_effect = [self.rules[0], second]
        with self.assertRaisesRegex(DacError, "Unsupported"):
            pull(client, [self.rules[0]["rule_id"], second["rule_id"]], self.temp.name)
        self.assertEqual(list(Path(self.temp.name).rglob("*.json")), [])

    def test_pull_requires_explicit_local_overwrite_and_keeps_path(self):
        path = Path(self.temp.name) / "existing.json"
        path.write_text(json.dumps(dict(self.rules[0], version=7)))
        client = Mock()
        client.request.return_value = self.rules[0]
        with self.assertRaisesRegex(DacError, "already exists"):
            pull(client, [self.rules[0]["rule_id"]], self.temp.name)
        pull(client, [self.rules[0]["rule_id"]], self.temp.name, overwrite=True)
        self.assertEqual(json.loads(path.read_text())["version"], 8)
        self.assertEqual(len(list(Path(self.temp.name).rglob("*.json"))), 1)

    def test_pull_requires_ui_ownership_and_rejects_prebuilt(self):
        for fields in ({"tags": []}, {"immutable": True}):
            client = Mock()
            client.request.return_value = dict(self.rules[0], **fields)
            with self.assertRaisesRegex(DacError, "custom rule"):
                pull(client, [self.rules[0]["rule_id"]], self.temp.name)
        self.assertEqual(list(Path(self.temp.name).rglob("*.json")), [])


if __name__ == "__main__":
    unittest.main()

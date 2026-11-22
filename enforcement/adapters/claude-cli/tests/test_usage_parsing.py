"""Claude adapter usage parsing/normalization tests (deterministic fixtures)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # claude-cli dir
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # adapters dir
import claude_adapter as adapter_mod  # noqa: E402
from agent_provider_contract import validation as v  # noqa: E402


# Faithful fixture derived from the observed real Claude CLI JSON output.
def provider_json(**over):
    obj = {
        "type": "result", "subtype": "success", "result": "OK",
        "total_cost_usd": 0.0786837,
        "usage": {
            "input_tokens": 2,
            "output_tokens": 4,
            "cache_creation_input_tokens": 19297,
            "cache_read_input_tokens": 14517,
            "output_tokens_details": {"thinking_tokens": 0},
        },
    }
    obj.update(over)
    return json.dumps(obj)


def base_request(**over):
    r = {"request_id": "r1", "work_unit_id": "wu-1",
         "schema": "ases-exec-request/1", "objective": "o",
         "working_directory": ".", "instructions": "i",
         "authorization_decision_ref": "a", "approved_scope_ref": "s",
         "config": {"provider": "claude-cli"}}
    r.update(over)
    return r


class ValidUsageTests(unittest.TestCase):
    def setUp(self):
        self.a = adapter_mod.ClaudeCliAdapter({})

    def test_complete_all_core(self):
        rec = self.a.normalize_usage(base_request(), provider_json())
        self.assertEqual(rec["completeness"], "complete")
        self.assertEqual(rec["input_tokens"], 2)
        self.assertEqual(rec["output_tokens"], 4)
        self.assertEqual(rec["cache_creation_input_tokens"], 19297)
        self.assertEqual(rec["cache_read_input_tokens"], 14517)

    def test_optional_present(self):
        rec = self.a.normalize_usage(base_request(), provider_json())
        self.assertEqual(rec["thinking_tokens"], 0)
        self.assertEqual(rec["total_cost_usd"], 0.0786837)

    def test_optional_absent(self):
        obj = json.loads(provider_json()); del obj["usage"]["output_tokens_details"]; del obj["total_cost_usd"]
        rec = self.a.normalize_usage(base_request(), json.dumps(obj))
        self.assertIsNone(rec["thinking_tokens"])
        self.assertIsNone(rec["total_cost_usd"])
        self.assertEqual(rec["completeness"], "complete")  # core still complete

    def test_core_zero(self):
        obj = json.loads(provider_json())
        obj["usage"] = {"input_tokens": 0, "output_tokens": 0,
                        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
        rec = self.a.normalize_usage(base_request(), json.dumps(obj))
        self.assertEqual(rec["completeness"], "complete")
        self.assertEqual(rec["input_tokens"], 0)

    def test_validates(self):
        rec = self.a.normalize_usage(base_request(), provider_json())
        v.validate_usage(rec)


class PartialUnavailableTests(unittest.TestCase):
    def setUp(self):
        self.a = adapter_mod.ClaudeCliAdapter({})

    def test_partial_one_core_missing(self):
        obj = json.loads(provider_json()); del obj["usage"]["cache_read_input_tokens"]
        rec = self.a.normalize_usage(base_request(), json.dumps(obj))
        self.assertEqual(rec["completeness"], "partial")
        self.assertIsNone(rec["cache_read_input_tokens"])

    def test_unavailable_all_core_null(self):
        obj = json.loads(provider_json())
        obj["usage"] = {"input_tokens": None, "output_tokens": None,
                        "cache_creation_input_tokens": None, "cache_read_input_tokens": None}
        rec = self.a.normalize_usage(base_request(), json.dumps(obj))
        self.assertEqual(rec["completeness"], "unavailable")
        self.assertEqual(rec["source"], "unavailable")

    def test_unavailable_no_usage_dict(self):
        obj = {"type": "result", "result": "OK"}
        rec = self.a.normalize_usage(base_request(), json.dumps(obj))
        self.assertEqual(rec["completeness"], "unavailable")

    def test_unavailable_no_output(self):
        rec = self.a.normalize_usage(base_request(), "")
        self.assertEqual(rec["completeness"], "unavailable")
        self.assertEqual(rec["source"], "unavailable")


class InvalidDataTests(unittest.TestCase):
    def setUp(self):
        self.a = adapter_mod.ClaudeCliAdapter({})

    def test_malformed_json(self):
        rec = self.a.normalize_usage(base_request(), "not json {")
        self.assertEqual(rec["completeness"], "unavailable")

    def test_invalid_numeric(self):
        obj = json.loads(provider_json()); obj["usage"]["input_tokens"] = "2"
        rec = self.a.normalize_usage(base_request(), json.dumps(obj))
        self.assertIsNone(rec["input_tokens"])

    def test_boolean_tokens(self):
        obj = json.loads(provider_json()); obj["usage"]["input_tokens"] = True
        rec = self.a.normalize_usage(base_request(), json.dumps(obj))
        self.assertIsNone(rec["input_tokens"])

    def test_negative_tokens(self):
        obj = json.loads(provider_json()); obj["usage"]["input_tokens"] = -1
        rec = self.a.normalize_usage(base_request(), json.dumps(obj))
        self.assertIsNone(rec["input_tokens"])

    def test_missing_attribution(self):
        rec = self.a.normalize_usage({"request_id": "r1"}, provider_json())
        self.assertIsNone(rec)  # no work_unit_id -> no record

    def test_result_validates(self):
        rec = self.a.normalize_usage(base_request(), provider_json())
        v.validate_usage(rec)  # must not raise


class LifecycleTests(unittest.TestCase):
    def test_execute_success_produces_usage(self):
        # mocked process producing valid JSON on stdout
        import tempfile, os, textwrap
        d = tempfile.mkdtemp(prefix="claude-fake-")
        script = os.path.join(d, "fake_claude.py")
        body = ("import json,sys\n"
                "print(json.dumps({'type':'result','result':'OK','total_cost_usd':0.01,"
                "'usage':{'input_tokens':1,'output_tokens':1,"
                "'cache_creation_input_tokens':10,'cache_read_input_tokens':5}}))\n"
                "sys.exit(0)\n")
        with open(script, "w") as f:
            f.write(body)
        a = adapter_mod.ClaudeCliAdapter({"executable": sys.executable, "timeout_seconds": 10})
        a.build_command = lambda req: [sys.executable, script, "-p", req["instructions"]]
        r = a.execute(base_request())
        self.assertEqual(r["status"], "SUCCEEDED")
        self.assertIsNotNone(a.last_usage)
        self.assertEqual(a.last_usage["completeness"], "complete")
        v.validate_usage(a.last_usage)

    def test_execute_failure_does_not_change_status(self):
        import tempfile, os
        d = tempfile.mkdtemp(prefix="claude-fake-")
        script = os.path.join(d, "fake_claude.py")
        with open(script, "w") as f:
            f.write("import sys; print('boom', file=sys.stderr); sys.exit(3)\n")
        a = adapter_mod.ClaudeCliAdapter({"executable": sys.executable, "timeout_seconds": 10})
        a.build_command = lambda req: [sys.executable, script, "-p", req["instructions"]]
        r = a.execute(base_request())
        self.assertEqual(r["status"], "FAILED")  # unchanged
        # stderr-only output -> no JSON on stdout -> unavailable usage, status stays FAILED
        self.assertEqual(a.last_usage["completeness"], "unavailable")

    def test_attribution_matches(self):
        a = adapter_mod.ClaudeCliAdapter({})
        rec = a.normalize_usage(base_request(request_id="X", work_unit_id="Y"), provider_json())
        self.assertEqual(rec["request_id"], "X")
        self.assertEqual(rec["work_unit_id"], "Y")
        self.assertEqual(rec["provider_id"], "claude-cli")


if __name__ == "__main__":
    unittest.main()

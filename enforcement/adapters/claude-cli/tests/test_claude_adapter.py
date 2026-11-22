"""Claude CLI Adapter tests: unit + mocked-process lifecycle (no real Claude)."""
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # claude-cli dir
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # adapters dir
import claude_adapter as adapter_mod  # noqa: E402
from agent_provider_contract import validation as v  # noqa: E402


def base_request(**over):
    r = {
        "schema": "ases-exec-request/1", "request_id": "r1", "work_unit_id": "wu-1",
        "authorization_decision_ref": "docs/governance/approvals/a.json",
        "approved_scope_ref": "docs/governance/CURRENT_TASK.md",
        "objective": "say hello", "working_directory": tempfile.gettempdir(), "instructions": "hello",
        "config": {"provider": "claude-cli", "permission_mode": "manual"},
    }
    r.update(over)
    return r


def make_adapter(body, timeout=2):
    """Build an adapter whose 'claude' is a fake Python script (mocked process)."""
    d = tempfile.mkdtemp(prefix="claude-fake-")
    script = os.path.join(d, "fake_claude.py")
    with open(script, "w") as f:
        f.write(textwrap.dedent(body))
    a = adapter_mod.ClaudeCliAdapter({"executable": sys.executable, "timeout_seconds": timeout})
    a._fake_script = script
    a.build_command = lambda req: [sys.executable, script, "-p", req["instructions"]]
    return a


class CommandConstructionTests(unittest.TestCase):
    def test_build_command(self):
        a = adapter_mod.ClaudeCliAdapter({})
        cmd = a.build_command(base_request(config={"provider": "claude-cli", "model": "sonnet",
                                                   "permission_mode": "manual", "allowed_tools": ["Read"]}))
        self.assertIn("claude", cmd[0].lower())  # resolved executable path
        self.assertIn("-p", cmd)
        self.assertIn("--output-format", cmd)
        self.assertIn("--model", cmd)
        self.assertIn("--permission-mode", cmd)
        self.assertIn("--allowedTools", cmd)
        self.assertEqual(cmd[-1], "hello")

    def test_identity_shape(self):
        a = adapter_mod.ClaudeCliAdapter({})
        ident = a.identity()
        self.assertEqual(ident["schema"], "ases-provider/1")
        self.assertEqual(ident["provider_id"], "claude-cli")
        self.assertIn("adapter_version", ident)


class ExecuteTests(unittest.TestCase):
    def test_start_failed(self):
        a = adapter_mod.ClaudeCliAdapter({"executable": "definitely-missing-claude-xyz", "timeout_seconds": 2})
        r = a.execute(base_request())
        self.assertEqual(r["status"], "FAILED")
        self.assertEqual(r["termination_reason"], "start-failed")
        self.assertEqual(r["exit_code"], None)
        self.assertTrue(any(e["scope"] == "provider" for e in r["errors"]))

    def test_invalid_request(self):
        a = adapter_mod.ClaudeCliAdapter({})
        r = a.execute({"instructions": "x"})  # missing required fields
        self.assertEqual(r["status"], "FAILED")
        self.assertEqual(r["termination_reason"], "start-failed")
        self.assertTrue(any(e["scope"] == "provider" and e["category"] == "invalid-request" for e in r["errors"]))

    def test_success(self):
        a = make_adapter("import sys; print('ok'); sys.exit(0)\n")
        r = a.execute(base_request())
        self.assertEqual(r["status"], "SUCCEEDED")
        self.assertEqual(r["exit_code"], 0)
        self.assertEqual(r["termination_reason"], "none")
        self.assertEqual(r["completed_utc"] is not None, True)

    def test_failure(self):
        a = make_adapter("import sys; print('boom', file=sys.stderr); sys.exit(3)\n")
        r = a.execute(base_request())
        self.assertEqual(r["status"], "FAILED")
        self.assertEqual(r["exit_code"], 3)
        self.assertTrue(any(e["scope"] == "provider" and e["category"] == "non-zero-exit" for e in r["errors"]))

    def test_timeout(self):
        a = make_adapter("import time; time.sleep(30)\n", timeout=1)
        r = a.execute(base_request())
        self.assertEqual(r["status"], "TIMED_OUT")
        self.assertEqual(r["termination_reason"], "timeout")
        self.assertEqual(r["termination_mechanism"], "Popen.kill")
        self.assertEqual(r["completed_utc"], None)
        self.assertTrue(any(e["scope"] == "termination" for e in r["errors"]))

    def test_result_invariants_hold(self):
        from agent_provider_contract import validation as v
        a = make_adapter("import sys; print('ok'); sys.exit(0)\n")
        r = a.execute(base_request())
        v.validate_result(r, base_request())


if __name__ == "__main__":
    unittest.main()

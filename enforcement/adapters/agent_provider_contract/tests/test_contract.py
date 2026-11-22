"""Tests for the Agent Provider Contract validation (stdlib-only)."""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent_provider_contract import validation as v  # noqa: E402


def base_result(**over):
    r = {
        "schema": v.RESULT_SCHEMA, "request_id": "r1", "work_unit_id": "wu-1", "provider_id": "claude-cli",
        "status": "SUCCEEDED", "exit_code": 0, "started_utc": "2026-11-22T13:00:00Z",
        "completed_utc": "2026-11-22T13:00:05Z", "terminated_utc": None,
        "termination_reason": "none", "termination_mechanism": None,
        "duration_seconds": 5.0, "output_ref": "out.json", "output_state": "complete",
        "evidence_ref": "ev.json", "evidence_state": "complete", "errors": [],
    }
    r.update(over)
    return r


class ProviderTests(unittest.TestCase):
    def test_valid(self):
        v.validate_provider({"schema": v.PROVIDER_SCHEMA, "provider_id": "claude-cli",
                             "provider_version": "2.1.322", "adapter_version": "1.0.0",
                             "capabilities": ["non-interactive"]})

    def test_missing_schema(self):
        with self.assertRaises(v.ValidationError):
            v.validate_provider({"provider_id": "claude-cli", "provider_version": "x", "adapter_version": "y"})

    def test_capabilities_not_list(self):
        with self.assertRaises(v.ValidationError):
            v.validate_provider({"schema": v.PROVIDER_SCHEMA, "provider_id": "c", "provider_version": "x",
                                 "adapter_version": "y", "capabilities": "not-a-list"})


class RequestTests(unittest.TestCase):
    def base(self, **over):
        r = {
            "schema": v.REQUEST_SCHEMA, "request_id": "r1", "work_unit_id": "wu-1",
            "authorization_decision_ref": "docs/governance/approvals/a.json",
            "approved_scope_ref": "docs/governance/CURRENT_TASK.md",
            "baseline_ref": "docs/governance/approvals/baseline.json", "intent_decision_ref": None,
            "objective": "do the thing", "working_directory": "C:/tmp", "instructions": "run it",
            "config": {"provider": "claude-cli", "permission_mode": "manual", "allowed_tools": ["Read"]},
        }
        r.update(over)
        return r

    def test_valid(self):
        v.validate_request(self.base())

    def test_missing_required(self):
        r = self.base(); del r["work_unit_id"]
        with self.assertRaises(v.ValidationError):
            v.validate_request(r)

    def test_unknown_config_field_fails_closed(self):
        r = self.base(); r["config"]["sandbox"] = "readonly"
        with self.assertRaises(v.ValidationError):
            v.validate_request(r)

    def test_missing_config_provider(self):
        r = self.base(); del r["config"]["provider"]
        with self.assertRaises(v.ValidationError):
            v.validate_request(r)


class ResultTests(unittest.TestCase):
    def test_succeeded(self):
        v.validate_result(base_result())

    def test_succeeded_collection_failed_stays_succeeded(self):
        r = base_result(output_state="unavailable", output_ref=None,
                        evidence_state="unavailable", evidence_ref=None,
                        errors=[{"scope": "output", "category": "read-fail", "message": "x"},
                                {"scope": "evidence", "category": "write-fail", "message": "y"}])
        self.assertEqual(v.validate_result(r)["status"], "SUCCEEDED")

    def test_succeeded_missing_exit_code_invalid(self):
        with self.assertRaises(v.ValidationError):
            v.validate_result(base_result(exit_code=None))

    def test_failed_ran(self):
        r = base_result(status="FAILED", exit_code=2, errors=[{"scope": "provider", "category": "non-zero-exit", "message": "x"}])
        v.validate_result(r)

    def test_failed_start(self):
        r = base_result(status="FAILED", exit_code=None, started_utc=None, completed_utc=None,
                        termination_reason="start-failed", output_state="none", output_ref=None,
                        evidence_state="unavailable", evidence_ref=None,
                        errors=[{"scope": "provider", "category": "start-failed", "message": "not found"},
                                {"scope": "evidence", "category": "none", "message": "no process"}])
        v.validate_result(r)

    def test_failed_start_with_started_utc_invalid(self):
        r = base_result(status="FAILED", exit_code=None, started_utc="2026-11-22T13:00:00Z",
                        completed_utc=None, termination_reason="start-failed",
                        errors=[{"scope": "provider", "category": "start-failed", "message": "x"}])
        with self.assertRaises(v.ValidationError):
            v.validate_result(r)

    def test_timed_out(self):
        r = base_result(status="TIMED_OUT", exit_code=None, completed_utc=None,
                        terminated_utc="2026-11-22T13:01:00Z", termination_reason="timeout",
                        termination_mechanism="Popen.kill", output_state="partial",
                        evidence_state="partial", evidence_ref="ev-partial.json",
                        errors=[{"scope": "termination", "category": "timeout", "message": "x"}])
        v.validate_result(r)

    def test_timed_out_reported_as_success_invalid(self):
        r = base_result(status="TIMED_OUT", completed_utc="2026-11-22T13:00:05Z", termination_reason="none")
        with self.assertRaises(v.ValidationError):
            v.validate_result(r)

    def test_interrupted_adapter_requires_mechanism(self):
        r = base_result(status="INTERRUPTED", exit_code=None, completed_utc=None,
                        terminated_utc="2026-11-22T13:01:00Z", termination_reason="interrupted",
                        termination_mechanism=None, errors=[{"scope": "termination", "category": "interrupted", "message": "x"}])
        with self.assertRaises(v.ValidationError):
            v.validate_result(r)

    def test_interrupted_external_mechanism_optional(self):
        r = base_result(status="INTERRUPTED", exit_code=None, completed_utc=None,
                        terminated_utc="2026-11-22T13:01:00Z", termination_reason="external",
                        termination_mechanism=None, errors=[{"scope": "termination", "category": "external-kill", "message": "x"}])
        v.validate_result(r)

    def test_unknown_no_termination_evidence(self):
        r = base_result(status="UNKNOWN", exit_code=None, completed_utc=None, terminated_utc=None,
                        termination_reason="lost-observability", output_state="unavailable", output_ref=None,
                        evidence_state="unavailable", evidence_ref=None,
                        errors=[{"scope": "observability", "category": "lost", "message": "x"},
                                {"scope": "output", "category": "none", "message": "x"},
                                {"scope": "evidence", "category": "none", "message": "x"}])
        v.validate_result(r)

    def test_unknown_cannot_be_complete_evidence(self):
        r = base_result(status="UNKNOWN", terminated_utc=None, termination_reason="lost-observability",
                        evidence_state="complete", evidence_ref="ev.json",
                        errors=[{"scope": "observability", "category": "lost", "message": "x"}])
        with self.assertRaises(v.ValidationError):
            v.validate_result(r)

    def test_request_identity_mismatch(self):
        req = {"request_id": "r1", "work_unit_id": "wu-1"}
        with self.assertRaises(v.ValidationError):
            v.validate_result(base_result(work_unit_id="wu-2"), req)


if __name__ == "__main__":
    unittest.main()

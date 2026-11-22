"""Tests for ases-usage/1 validation."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent_provider_contract import validation as v  # noqa: E402


def usage(**over):
    r = {
        "schema": v.USAGE_SCHEMA, "request_id": "r1", "work_unit_id": "wu-1", "provider_id": "claude-cli",
        "source": "provider-reported", "completeness": "complete",
        "input_tokens": 2, "output_tokens": 4,
        "cache_creation_input_tokens": 19297, "cache_read_input_tokens": 14517,
        "thinking_tokens": None, "total_cost_usd": None,
        "captured_utc": "2026-11-22T14:00:00Z", "raw_ref": None,
    }
    r.update(over)
    return r


class UsageValidationTests(unittest.TestCase):
    def test_complete_core_present_optional_null(self):
        v.validate_usage(usage())

    def test_complete_optional_zero(self):
        v.validate_usage(usage(thinking_tokens=0, total_cost_usd=0.0786837))

    def test_complete_core_null_rejected(self):
        with self.assertRaises(v.ValidationError):
            v.validate_usage(usage(cache_read_input_tokens=None))

    def test_partial_at_least_one_core(self):
        v.validate_usage(usage(completeness="partial", output_tokens=None,
                               cache_creation_input_tokens=None, cache_read_input_tokens=None))

    def test_partial_all_core_null_rejected(self):
        with self.assertRaises(v.ValidationError):
            v.validate_usage(usage(completeness="partial", input_tokens=None, output_tokens=None,
                                   cache_creation_input_tokens=None, cache_read_input_tokens=None))

    def test_unavailable(self):
        v.validate_usage(usage(source="unavailable", completeness="unavailable",
                               input_tokens=None, output_tokens=None,
                               cache_creation_input_tokens=None, cache_read_input_tokens=None))

    def test_unavailable_with_core_present_rejected(self):
        with self.assertRaises(v.ValidationError):
            v.validate_usage(usage(source="unavailable", completeness="unavailable"))

    def test_source_unavailable_requires_unavailable_completeness(self):
        with self.assertRaises(v.ValidationError):
            v.validate_usage(usage(source="unavailable", completeness="complete"))

    def test_complete_source_unavailable_rejected(self):
        with self.assertRaises(v.ValidationError):
            v.validate_usage(usage(source="unavailable"))

    def test_negative_tokens_rejected(self):
        with self.assertRaises(v.ValidationError):
            v.validate_usage(usage(input_tokens=-1))

    def test_non_integer_tokens_rejected(self):
        with self.assertRaises(v.ValidationError):
            v.validate_usage(usage(input_tokens=2.5))

    def test_string_tokens_rejected(self):
        with self.assertRaises(v.ValidationError):
            v.validate_usage(usage(input_tokens="2"))

    def test_bool_tokens_rejected(self):
        with self.assertRaises(v.ValidationError):
            v.validate_usage(usage(input_tokens=True))

    def test_missing_required_field(self):
        r = usage(); del r["work_unit_id"]
        with self.assertRaises(v.ValidationError):
            v.validate_usage(r)

    def test_invalid_source(self):
        with self.assertRaises(v.ValidationError):
            v.validate_usage(usage(source="verified"))

    def test_negative_cost_rejected(self):
        with self.assertRaises(v.ValidationError):
            v.validate_usage(usage(total_cost_usd=-0.1))

    def test_deterministic_same_input_same_result(self):
        self.assertEqual(v.validate_usage(usage()), v.validate_usage(usage()))


if __name__ == "__main__":
    unittest.main()

"""Budget policy validation tests."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from token_efficiency import policy as P  # noqa: E402


def pol(**over):
    r = {"schema": P.POLICY_SCHEMA, "policy_id": "p1", "policy_version": "1",
         "scope": "work-unit", "metric": "tokens",
         "warning_threshold": 100000, "block_threshold": 200000}
    r.update(over)
    return r


class PolicyTests(unittest.TestCase):
    def test_valid(self):
        P.validate_policy(pol())

    def test_missing_policy(self):
        with self.assertRaises(P.PolicyError):
            P.validate_policy(None)

    def test_invalid_policy_not_dict(self):
        with self.assertRaises(P.PolicyError):
            P.validate_policy("not-a-policy")

    def test_missing_required_threshold(self):
        with self.assertRaises(P.PolicyError):
            P.validate_policy(pol(warning_threshold=None, block_threshold=None))

    def test_contradictory_threshold(self):
        with self.assertRaises(P.PolicyError):
            P.validate_policy(pol(warning_threshold=300000, block_threshold=200000))

    def test_unsupported_metric(self):
        with self.assertRaises(P.PolicyError):
            P.validate_policy(pol(metric="bananas"))

    def test_unsupported_scope(self):
        with self.assertRaises(P.PolicyError):
            P.validate_policy(pol(scope="everything"))

    def test_deterministic(self):
        self.assertEqual(P.validate_policy(pol()), P.validate_policy(pol()))


if __name__ == "__main__":
    unittest.main()

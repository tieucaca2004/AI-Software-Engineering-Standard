"""Contract tests for the AI instruction adapters."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = [
    ROOT / "AGENTS.md",
    ROOT / "CLAUDE.md",
    ROOT / "enforcement" / "copilot-instructions.md",
    ROOT / "enforcement" / "cursor" / "ases.mdc",
    ROOT / "enforcement" / "generic" / "PROJECT_AI_INSTRUCTIONS.md",
]


class AdapterContracts(unittest.TestCase):
    def test_every_adapter_requires_constitution_context_and_task(self):
        for path in ADAPTERS:
            with self.subTest(path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("CONSTITUTION.md", text)
                self.assertIn("PROJECT_CONTEXT.md", text)
                self.assertIn("CURRENT_TASK.md", text)
                self.assertIn("ases_gate.py", text)

    def test_every_adapter_preserves_founder_authority(self):
        for path in ADAPTERS:
            with self.subTest(path.name):
                text = path.read_text(encoding="utf-8").lower()
                self.assertIn("founder", text)
                self.assertTrue("self-approve" in text or "self approve" in text)

    def test_no_adapter_grants_permission_to_bypass(self):
        banned = ("bypass branch protection", "force-push is allowed", "merge without approval")
        for path in ADAPTERS:
            with self.subTest(path.name):
                text = path.read_text(encoding="utf-8").lower()
                for phrase in banned:
                    self.assertNotIn(phrase, text)

    def test_cursor_rule_is_always_applied(self):
        text = (ROOT / "enforcement" / "cursor" / "ases.mdc").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("alwaysApply: true", text)

    def test_copilot_names_the_snapshot_constitution(self):
        text = (ROOT / "enforcement" / "copilot-instructions.md").read_text(encoding="utf-8")
        self.assertIn("docs/governance/ases/CONSTITUTION.md", text)


if __name__ == "__main__":
    unittest.main()

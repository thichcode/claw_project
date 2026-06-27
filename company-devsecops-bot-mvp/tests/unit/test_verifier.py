import unittest

from app.orchestrator.verifier import verify_completion


class TestVerifier(unittest.TestCase):
    def test_verify_completed(self):
        ok, msg = verify_completion([
            {"status": "completed"},
            {"status": "completed"},
        ])
        self.assertTrue(ok)
        self.assertIn("completed", msg.lower())

    def test_verify_failed(self):
        ok, msg = verify_completion([
            {"status": "completed"},
            {"status": "failed"},
        ])
        self.assertFalse(ok)
        self.assertIn("failed", msg.lower())


if __name__ == "__main__":
    unittest.main()

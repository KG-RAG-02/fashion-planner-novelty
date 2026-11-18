"""응답 원장(workflow_response)의 동시 저장.

같은 request ID의 두 요청이 동시에 save_response에 들어오면 먼저 커밋한 응답이 결과가 되어야 한다.
다른 연결이 쓰기 잠금을 쥔 채 행을 넣은 상황을 직접 만들어, 시간에 기대지 않고 경쟁을 재현한다.
"""
import json
import sqlite3
import tempfile
import threading
import time
import unittest

from fashion_planner_novelty.workflows.draft_artifacts import DraftArtifactStore, RequestReplayConflict


class ConcurrentSaveResponseTests(unittest.TestCase):
    def save_while_another_writer_commits(self, source_sha256):
        """다른 연결이 같은 request ID 행을 넣고 커밋하기 직전에 save_response를 부른다."""
        with tempfile.TemporaryDirectory() as directory:
            store = DraftArtifactStore(directory)
            store.save_response("warm-up", "sha-warm-up", {"ready": True})  # 표를 만들어 둔다
            writer = sqlite3.connect(store.db, timeout=15, isolation_level=None)
            try:
                writer.execute("BEGIN IMMEDIATE")
                writer.execute("INSERT INTO workflow_response VALUES (?,?,?)",
                               ("request-1", "sha-first", json.dumps({"saved_by": "first"})))
                outcome = {}

                def second():
                    try:
                        outcome["value"] = store.save_response("request-1", source_sha256, {"saved_by": "second"})
                    except Exception as exc:  # 테스트가 예외 종류를 확인한다
                        outcome["error"] = exc

                thread = threading.Thread(target=second)
                thread.start()
                time.sleep(0.3)  # 두 번째 요청이 원장에 닿을 시간을 준다
                writer.execute("COMMIT")
                thread.join(timeout=10)
                self.assertFalse(thread.is_alive())
                return outcome
            finally:
                writer.close()

    def test_the_second_identical_request_returns_the_first_saved_response(self):
        outcome = self.save_while_another_writer_commits("sha-first")
        self.assertNotIn("error", outcome, outcome.get("error"))
        self.assertEqual(outcome["value"], {"saved_by": "first"})

    def test_a_different_payload_under_the_same_request_id_is_a_replay_conflict(self):
        outcome = self.save_while_another_writer_commits("sha-other")
        self.assertIsInstance(outcome.get("error"), RequestReplayConflict)


if __name__ == "__main__":
    unittest.main()

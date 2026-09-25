"""`omh_resume`: pick up this person's earlier work from another surface.

The plans and checkpoints are declared through the real `omh_todo` tool into a
temp OMH home, and the sessions that declared them are rows in a temp Hermes
`state.db`, so the reader is exercised against the records it will meet in a
live profile. Who counts as the same person is read only from the session
rows: local surfaces share the profile's user, a chat platform user is its own
`source` + `user_id`, and a session another profile's `state.db` lists is
never shown.
"""
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from _local_package import load_local_package

load_local_package()

from omh.plugin_bundle.omh import work_resume  # noqa: E402
from omh.plugin_bundle.omh.tools.resume_tool import omh_resume_handler  # noqa: E402
from omh.plugin_bundle.omh.tools.todo_tool import omh_todo_handler  # noqa: E402

_COLUMNS = (
    "id TEXT PRIMARY KEY, source TEXT NOT NULL, user_id TEXT, started_at REAL NOT NULL, "
    "ended_at REAL, last_activity_at REAL, message_count INTEGER, tool_call_count INTEGER, "
    "git_branch TEXT, git_repo_root TEXT, title TEXT, last_activity_description TEXT, "
    "chat_type TEXT, model_config TEXT, archived INTEGER"
)


def _state_db(home: Path, rows: list[dict]) -> None:
    home.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(home / "state.db")
    connection.execute(f"CREATE TABLE sessions ({_COLUMNS})")
    for row in rows:
        connection.execute(
            "INSERT INTO sessions (id, source, user_id, started_at, ended_at, last_activity_at, "
            "message_count, tool_call_count, git_branch, git_repo_root, title, last_activity_description, "
            "chat_type, model_config, archived) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (row["id"], row["source"], row.get("user_id"), row.get("started_at", time.time() - 7200),
             row.get("ended_at"), row.get("last_activity_at", time.time() - 3600), row.get("message_count", 12),
             row.get("tool_call_count", 9), row.get("git_branch"), row.get("git_repo_root"),
             row.get("title", "PRIVATE TITLE the person typed"), "PRIVATE ACTIVITY TEXT",
             row.get("chat_type"), row.get("model_config"), row.get("archived", 0)),
        )
    connection.commit()
    connection.close()


class WorkResumeTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.omh = self.root / "omh"
        self.hermes = self.root / "hermes"
        env = patch.dict(os.environ, {"OMH_HOME": str(self.omh), "HERMES_HOME": str(self.hermes)})
        env.start()
        self.addCleanup(env.stop)
        cwd = patch("omh.plugin_bundle.omh.runtime_paths.runtime_cwd", return_value=self.root)
        cwd.start()
        self.addCleanup(cwd.stop)

    def declare(self, session: str, texts=("Parser fix", "Regression test", "Docs"), done: int = 1):
        items = [{"text": text, "state": "done" if i < done else ("active" if i == done else "pending")}
                 for i, text in enumerate(texts)]
        result = json.loads(omh_todo_handler({"action": "set", "title": "Ship parser", "items": items},
                                             session_id=session))
        self.assertEqual(result["status"], "written", result)

    def resume(self, session: str, **args) -> dict:
        return json.loads(omh_resume_handler(args, session_id=session))

    def test_desktop_session_picks_up_the_tui_plan(self):
        _state_db(self.hermes, [
            {"id": "tui-1", "source": "tui", "git_branch": "feature/parser", "git_repo_root": "/work/oh-my-hermes"},
            {"id": "desk-1", "source": "desktop"},
        ])
        self.declare("tui-1")
        result = self.resume("desk-1")
        self.assertEqual(result["status"], "found", result)
        self.assertEqual(result["realm"], "local")
        [entry] = result["work"]
        self.assertEqual((entry["surface"], entry["repo"], entry["branch"]), ("tui", "oh-my-hermes", "feature/parser"))
        self.assertEqual([item["state"] for item in entry["plan"]["items"]], ["done", "active", "pending"])
        text = result["text"]
        self.assertIn("tui session in oh-my-hermes on feature/parser", text)
        self.assertIn('Plan "Ship parser": 1 of 3 declared done', text)
        self.assertIn("[x] Parser fix", text)
        self.assertIn("[>] Regression test", text)
        self.assertIn("not observed results", text)
        # Metadata only: free text Hermes stores beside the row never leaves it.
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_checkpoint_outlives_the_plan_and_is_linked_to_its_session(self):
        _state_db(self.hermes, [{"id": "tui-1", "source": "tui"}, {"id": "cli-1", "source": "cli"}])
        self.declare("tui-1")
        checkpoint = json.loads(omh_todo_handler(
            {"action": "checkpoint", "accepted": True, "revision": "rev-a", "environment": "fixture"},
            session_id="tui-1"))
        self.assertEqual(checkpoint["status"], "written", checkpoint)
        json.loads(omh_todo_handler({"action": "clear"}, session_id="tui-1"))
        result = self.resume("cli-1")
        self.assertEqual(result["status"], "found", result)
        [entry] = result["work"]
        self.assertIsNone(entry["plan"])
        [dossier] = entry["checkpoints"]
        self.assertEqual(dossier["checkpoint_id"], checkpoint["checkpoint"]["checkpoint_id"])
        self.assertEqual(dossier["item_count"], 3)
        self.assertIn("verification absent", result["text"])

    def test_no_prior_work_says_so(self):
        _state_db(self.hermes, [{"id": "tui-1", "source": "tui"}, {"id": "desk-1", "source": "desktop"}])
        result = self.resume("desk-1")
        self.assertEqual(result["status"], "none")
        self.assertEqual(result["work"], [])
        self.assertIn("No earlier OMH work is recorded", result["text"])

    def test_own_session_plan_is_not_earlier_work(self):
        _state_db(self.hermes, [{"id": "desk-1", "source": "desktop"}])
        self.declare("desk-1")
        self.assertEqual(self.resume("desk-1")["status"], "none")

    def test_another_profiles_work_is_not_shown(self):
        # Both profiles share one OMH home; only this profile's state.db decides.
        _state_db(self.hermes, [{"id": "desk-1", "source": "desktop"}])
        _state_db(self.root / "other-profile", [{"id": "tui-other", "source": "tui"}])
        self.declare("tui-other")
        checkpoint = json.loads(omh_todo_handler(
            {"action": "checkpoint", "accepted": True, "revision": "rev-a", "environment": "fixture"},
            session_id="tui-other"))
        self.assertEqual(checkpoint["status"], "written", checkpoint)
        self.assertTrue(any((self.omh / "runtime" / "todos").iterdir()))
        result = self.resume("desk-1")
        self.assertEqual(result["status"], "none", result)
        self.assertNotIn("Parser fix", result["text"])
        self.assertNotIn(checkpoint["checkpoint"]["checkpoint_id"], result["text"])
        # A session of this profile that declared nothing does not inherit it.
        self.declare("desk-2", texts=("Mine",))
        with sqlite3.connect(self.hermes / "state.db") as connection:
            connection.execute("INSERT INTO sessions (id, source, started_at, last_activity_at) VALUES "
                               "('desk-2', 'desktop', ?, ?)", (time.time() - 60, time.time() - 60))
        connection.close()
        [entry] = self.resume("desk-1")["work"]
        self.assertEqual(entry["checkpoints"], [])

    def test_chat_user_sees_only_their_own_threads(self):
        _state_db(self.hermes, [
            {"id": "slack-a1", "source": "slack", "user_id": "U_A", "chat_type": "dm"},
            {"id": "slack-a2", "source": "slack", "user_id": "U_A", "chat_type": "dm"},
            {"id": "slack-b1", "source": "slack", "user_id": "U_B", "chat_type": "dm"},
            {"id": "slack-a-group", "source": "slack", "user_id": "U_A", "chat_type": "group"},
            {"id": "tui-1", "source": "tui"},
            {"id": "discord-a", "source": "discord", "user_id": "U_A", "chat_type": "dm"},
        ])
        self.declare("slack-a1", texts=("Mine",))
        self.declare("slack-b1", texts=("Someone else",))
        self.declare("tui-1", texts=("Owner local",))
        self.declare("discord-a", texts=("Other platform",))
        self.declare("slack-a-group", texts=("Said in a channel",))
        result = self.resume("slack-a2")
        self.assertEqual(result["realm"], "messaging")
        self.assertEqual([entry["surface"] for entry in result["work"]], ["slack"])
        self.assertIn("Mine", result["text"])
        for foreign in ("Someone else", "Owner local", "Other platform", "Said in a channel"):
            self.assertNotIn(foreign, result["text"])
        # And the local user does not see the chat user's work either.
        local = self.resume("tui-1")
        self.assertEqual(local["status"], "none", local)

    def test_surface_without_a_person_is_shown_nothing(self):
        _state_db(self.hermes, [{"id": "tui-1", "source": "tui"}, {"id": "hook-1", "source": "webhook"},
                                {"id": "slack-anon", "source": "slack", "chat_type": "dm"},
                                {"id": "slack-room", "source": "slack", "user_id": "U_A", "chat_type": "group"},
                                {"id": "slack-thread", "source": "slack", "user_id": "U_A", "chat_type": "thread"},
                                {"id": "tui-child", "source": "tui",
                                 "model_config": json.dumps({"_delegate_from": "tui-1"})}])
        self.declare("tui-1")
        # A shared room names one user while anyone there can ask, so it is
        # refused even for the user its row names; a delegated child is not a person.
        for session in ("hook-1", "slack-anon", "slack-room", "slack-thread", "tui-child"):
            with self.subTest(session=session):
                result = self.resume(session)
                self.assertEqual(result["status"], "unlinked_surface")
                self.assertEqual(result["work"], [])
                self.assertNotIn("Parser fix", result["text"])

    def test_unknown_or_missing_session_fails_closed(self):
        _state_db(self.hermes, [{"id": "tui-1", "source": "tui"}])
        self.declare("tui-1")
        self.assertEqual(self.resume("never-recorded")["status"], "session_not_observed")
        self.assertEqual(json.loads(omh_resume_handler({}))["status"], "no_session")
        # The model cannot name a session: only the host dispatch kwarg counts.
        self.assertEqual(json.loads(omh_resume_handler({"session_id": "tui-1"}))["status"], "no_session")

    def test_missing_state_db_is_unavailable_not_empty(self):
        self.declare("tui-1")
        result = self.resume("desk-1")
        self.assertEqual(result["status"], "store_unavailable")
        self.assertNotIn("Parser fix", result["text"])

    def test_delegated_and_archived_sessions_are_not_earlier_work(self):
        _state_db(self.hermes, [
            {"id": "tui-child", "source": "tui", "model_config": json.dumps({"_delegate_from": "tui-x"})},
            {"id": "tui-archived", "source": "tui", "archived": 1},
            {"id": "desk-1", "source": "desktop"},
        ])
        self.declare("tui-child", texts=("Child lane",))
        self.declare("tui-archived", texts=("Archived",))
        self.assertEqual(self.resume("desk-1")["status"], "none")

    def test_checkpoint_older_than_thirty_days_is_not_shown(self):
        _state_db(self.hermes, [{"id": "tui-1", "source": "tui"}, {"id": "desk-1", "source": "desktop"}])
        self.declare("tui-1")
        checkpoint = json.loads(omh_todo_handler(
            {"action": "checkpoint", "accepted": True, "revision": "rev-a", "environment": "fixture"},
            session_id="tui-1"))
        self.assertEqual(checkpoint["status"], "written", checkpoint)
        json.loads(omh_todo_handler({"action": "clear"}, session_id="tui-1"))
        later = time.time() + work_resume.CHECKPOINT_STALE_SECONDS + 60
        # The session row stays active, so only the checkpoint's own age decides.
        with sqlite3.connect(self.hermes / "state.db") as connection:
            connection.execute("UPDATE sessions SET last_activity_at = ? WHERE id = 'tui-1'", (later - 60,))
        connection.close()
        payload = work_resume.read_work_resume(self.omh, self.hermes, "desk-1", now=later)
        self.assertEqual(payload["status"], "none", payload)

    def test_credential_in_a_plan_item_is_redacted(self):
        _state_db(self.hermes, [{"id": "tui-1", "source": "tui"}, {"id": "desk-1", "source": "desktop"}])
        secret = "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456"
        self.declare("tui-1", texts=("Rotate token", secret))
        result = self.resume("desk-1")
        self.assertEqual(result["status"], "found", result)
        self.assertNotIn(secret, json.dumps(result))
        self.assertIn("[redacted]", result["text"])

    def test_stale_plan_is_not_resumed(self):
        _state_db(self.hermes, [{"id": "tui-1", "source": "tui"}, {"id": "desk-1", "source": "desktop"}])
        self.declare("tui-1")
        later = time.time() + work_resume.TODO_STALE_SECONDS + 60
        payload = work_resume.read_work_resume(self.omh, self.hermes, "desk-1", now=later)
        self.assertEqual(payload["status"], "none", payload)

    def test_newest_first_and_limit(self):
        _state_db(self.hermes, [{"id": "tui-old", "source": "tui"}, {"id": "tui-new", "source": "tui"},
                                {"id": "desk-1", "source": "desktop"}])
        self.declare("tui-old", texts=("Older",))
        todos = self.omh / "runtime" / "todos"
        old_file = next(path for path in todos.iterdir() if path.name.startswith("tui-old"))
        data = json.loads(old_file.read_text())
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 7200))
        old_file.write_text(json.dumps(data), encoding="utf-8")
        self.declare("tui-new", texts=("Newer",))
        result = self.resume("desk-1")
        self.assertEqual([entry["plan"]["items"][0]["text"] for entry in result["work"]], ["Newer", "Older"])
        self.assertEqual(len(self.resume("desk-1", limit=1)["work"]), 1)


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class BattleCodeLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, max_unlocked_layer) VALUES ('library_user', 'x', ?, 4)",
                (now,),
            )
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, max_unlocked_layer) VALUES ('other_user', 'x', ?, 4)",
                (now,),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = 'library_user'").fetchone()["id"])
            self.other_user_id = int(db.execute("SELECT id FROM users WHERE username = 'other_user'").fetchone()["id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self, user_id=None):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = user_id or self.user_id
            session["username"] = "library_user"
        return client

    def test_library_save_select_unselect_and_page(self):
        client = self._client()
        resp = client.post(
            "/modules/battle-codes/save",
            data={
                "slot_number": "1",
                "condition_key": "after_miss",
                "effect_key": "guaranteed_hit",
                "usage_label": "stable",
            },
            follow_redirects=True,
        )
        body = resp.get_data(as_text=True)
        self.assertIn("CODE-01", body)
        self.assertIn("安定重視", body)
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT * FROM battle_code_library WHERE user_id = ? AND deleted_at IS NULL", (self.user_id,)).fetchone()
            self.assertEqual(row["slot_number"], 1)
            self.assertEqual(row["is_selected"], 0)
            code_id = int(row["id"])
        client.post("/modules/battle-codes/select", data={"battle_code_id": str(code_id)})
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT is_selected FROM battle_code_library WHERE id = ?", (code_id,)).fetchone()
            user = db.execute("SELECT selected_battle_code_condition_key FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(row["is_selected"], 1)
            self.assertEqual(user["selected_battle_code_condition_key"], "after_miss")
        client.post("/modules/battle-codes/unselect")
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT is_selected FROM battle_code_library WHERE id = ?", (code_id,)).fetchone()
            self.assertEqual(row["is_selected"], 0)

    def test_overwrite_keeps_old_stats_separate_and_label_update_does_not_replace(self):
        client = self._client()
        client.post(
            "/modules/battle-codes/save",
            data={"slot_number": "1", "condition_key": "after_miss", "effect_key": "guaranteed_hit", "usage_label": "stable"},
        )
        client.post(
            "/modules/battle-codes/save",
            data={"slot_number": "1", "condition_key": "after_miss", "effect_key": "guaranteed_hit", "usage_label": "boss"},
        )
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertEqual(int(db.execute("SELECT COUNT(*) AS c FROM battle_code_library").fetchone()["c"]), 1)
            row = db.execute("SELECT usage_label FROM battle_code_library WHERE user_id = ?", (self.user_id,)).fetchone()
            self.assertEqual(row["usage_label"], "boss")
        client.post(
            "/modules/battle-codes/save",
            data={"slot_number": "1", "condition_key": "battle_start", "effect_key": "attack_up_15", "usage_label": "speed"},
        )
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertEqual(int(db.execute("SELECT COUNT(*) AS c FROM battle_code_library").fetchone()["c"]), 2)
            deleted = db.execute("SELECT deleted_at FROM battle_code_library WHERE effect_key = 'guaranteed_hit'").fetchone()
            active = db.execute("SELECT * FROM battle_code_library WHERE deleted_at IS NULL").fetchone()
            self.assertIsNotNone(deleted["deleted_at"])
            self.assertEqual(active["condition_key"], "battle_start")

    def test_migrates_legacy_selected_code_once(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                UPDATE users
                SET selected_battle_code_condition_key = 'after_miss',
                    selected_battle_code_effect_key = 'guaranteed_hit',
                    selected_battle_code_updated_at = ?
                WHERE id = ?
                """,
                (int(time.time()), self.user_id),
            )
            db.commit()
        client = self._client()
        body = client.get("/modules/battle-codes").get_data(as_text=True)
        self.assertIn("移行しました", body)
        client.get("/modules/battle-codes")
        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(db.execute("SELECT COUNT(*) AS c FROM battle_code_library WHERE user_id = ?", (self.user_id,)).fetchone()["c"])
            self.assertEqual(count, 1)

    def test_other_user_cannot_select_or_delete(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            result = game_app._battle_code_library_save(db, self.other_user_id, 1, "after_miss", "guaranteed_hit", "stable")
            code_id = int(result["code"]["id"])
            db.commit()
        client = self._client(self.user_id)
        client.post("/modules/battle-codes/select", data={"battle_code_id": str(code_id)})
        client.post("/modules/battle-codes/delete", data={"battle_code_id": str(code_id)})
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT is_selected, deleted_at FROM battle_code_library WHERE id = ?", (code_id,)).fetchone()
            self.assertEqual(row["is_selected"], 0)
            self.assertIsNone(row["deleted_at"])

    def test_stats_update_is_idempotent_per_battle_result(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            result = game_app._battle_code_library_save(db, self.user_id, 1, "battle_start", "attack_up_15", "general")
            code = result["code"]
            summary = {
                "condition_event_count": 1,
                "activation_count": 1,
                "effect_totals": {"bonus_damage": 12, "healing_amount": 0, "guaranteed_hit": 0, "damage_reduced": 0, "critical_bonus": 0},
            }
            self.assertTrue(game_app._battle_code_library_stats_update(db, self.user_id, code, summary, battle_result_id="battle-1", result_win=True, is_boss=False, turn_count=3))
            self.assertFalse(game_app._battle_code_library_stats_update(db, self.user_id, code, summary, battle_result_id="battle-1", result_win=True, is_boss=False, turn_count=3))
            db.commit()
            stats = db.execute("SELECT * FROM battle_code_stats WHERE battle_code_library_id = ?", (code["id"],)).fetchone()
            self.assertEqual(stats["use_count"], 1)
            self.assertEqual(stats["win_count"], 1)
            self.assertEqual(stats["activation_count"], 1)
            self.assertEqual(stats["total_bonus_damage"], 12)


if __name__ == "__main__":
    unittest.main()

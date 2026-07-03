import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class ModuleRerollV2Tests(unittest.TestCase):
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
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer, coins)
                VALUES (?, ?, ?, 0, 0, 4, 1000)
                """,
                ("reroll_v2_user", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("reroll_v2_user",)).fetchone()["id"])
            module = game_app._grant_research_module_instance(db, self.user_id, "sniper_prototype", source="test")
            self.module_id = int(module["instance_id"])
            db.execute(
                """
                UPDATE user_research_modules
                SET hp_bonus = 0, atk_bonus = 40, def_bonus = 36, spd_bonus = 0, acc_bonus = 0, cri_bonus = 0
                WHERE id = ?
                """,
                (self.module_id,),
            )
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "reroll_v2_user"
        return client

    def _stats(self, db):
        row = db.execute(
            "SELECT hp_bonus, atk_bonus, def_bonus, spd_bonus, acc_bonus, cri_bonus FROM user_research_modules WHERE id = ?",
            (self.module_id,),
        ).fetchone()
        return {key: int(row[key] or 0) for key in row.keys()}

    def test_create_candidate_spends_coins_without_changing_module(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            before = self._stats(db)
            result = game_app.execute_research_module_reroll(db, self.user_id, self.module_id)
            self.assertTrue(result["ok"])
            after = self._stats(db)
            coins = int(db.execute("SELECT coins FROM users WHERE id = ?", (self.user_id,)).fetchone()["coins"])
            self.assertEqual(before, after)
            self.assertEqual(coins, 900)
            self.assertGreaterEqual(result["candidate_total"], round(76 * 0.95))
            self.assertLessEqual(result["candidate_total"], round(76 * 1.05))
            self.assertGreaterEqual(max(result["candidate_stats"].values()), 10)
            event = db.execute(
                "SELECT id FROM world_events_log WHERE event_type = ? AND user_id = ?",
                (game_app.AUDIT_EVENT_TYPES["MODULE_REROLL_CANDIDATE_CREATE"], self.user_id),
            ).fetchone()
            self.assertIsNotNone(event)

    def test_accept_updates_module_and_reject_keeps_module(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            created = game_app.execute_research_module_reroll(db, self.user_id, self.module_id)
            accepted = game_app.accept_module_reroll_candidate(db, self.user_id, created["candidate_id"])
            self.assertTrue(accepted["ok"])
            accepted_stats = self._stats(db)
            self.assertEqual(sum(accepted_stats.values()), created["candidate_total"])
            accept_event = db.execute(
                "SELECT id FROM world_events_log WHERE event_type = ? AND user_id = ?",
                (game_app.AUDIT_EVENT_TYPES["MODULE_REROLL_ACCEPT"], self.user_id),
            ).fetchone()
            self.assertIsNotNone(accept_event)

            module2 = game_app._grant_research_module_instance(db, self.user_id, "sniper_prototype", source="test")
            module2_id = int(module2["instance_id"])
            db.execute(
                """
                UPDATE user_research_modules
                SET hp_bonus = 0, atk_bonus = 30, def_bonus = 40, spd_bonus = 0, acc_bonus = 0, cri_bonus = 0
                WHERE id = ?
                """,
                (module2_id,),
            )
            db.execute("UPDATE users SET coins = 1000 WHERE id = ?", (self.user_id,))
            db.commit()
            created2 = game_app.execute_research_module_reroll(db, self.user_id, module2_id)
            rejected = game_app.reject_module_reroll_candidate(db, self.user_id, created2["candidate_id"])
            self.assertTrue(rejected["ok"])
            row = db.execute("SELECT atk_bonus, def_bonus FROM user_research_modules WHERE id = ?", (module2_id,)).fetchone()
            self.assertEqual(int(row["atk_bonus"] or 0), 30)
            self.assertEqual(int(row["def_bonus"] or 0), 40)
            reject_event = db.execute(
                "SELECT id FROM world_events_log WHERE event_type = ? AND user_id = ?",
                (game_app.AUDIT_EVENT_TYPES["MODULE_REROLL_REJECT"], self.user_id),
            ).fetchone()
            self.assertIsNotNone(reject_event)

    def test_pending_expired_and_locked_safety(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            created = game_app.execute_research_module_reroll(db, self.user_id, self.module_id)
            second = game_app.execute_research_module_reroll(db, self.user_id, self.module_id)
            self.assertFalse(second["ok"])
            self.assertIn("未決定", second["reason"])
            db.execute("UPDATE module_reroll_candidates SET expires_at = ? WHERE id = ?", (int(time.time()) - 1, created["candidate_id"]))
            db.commit()
            expired = game_app.accept_module_reroll_candidate(db, self.user_id, created["candidate_id"])
            self.assertFalse(expired["ok"])
            self.assertIn("期限切れ", expired["reason"])

            locked = game_app._grant_research_module_instance(db, self.user_id, "sniper_prototype", source="test")
            locked_id = int(locked["instance_id"])
            db.execute("UPDATE user_research_modules SET is_locked = 1 WHERE id = ?", (locked_id,))
            db.commit()
            _module, error = game_app._validate_research_module_reroll_target(db, self.user_id, locked_id)
            self.assertIn("保護中", error)

    def test_v2_http_routes(self):
        client = self._client()
        confirm = client.get(f"/modules/reroll/confirm/{self.module_id}")
        self.assertEqual(confirm.status_code, 200)
        html = confirm.get_data(as_text=True)
        self.assertIn("配分再調整", html)
        self.assertIn("現在合計", html)
        with client.session_transaction() as session:
            token = session[f"module_reroll_token:{self.module_id}"]
        created = client.post("/modules/reroll/create", data={"module_instance_id": self.module_id, "reroll_token": token})
        self.assertEqual(created.status_code, 200)
        html = created.get_data(as_text=True)
        self.assertIn("採用する", html)
        self.assertIn("今のままにする", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            candidate_id = int(db.execute("SELECT id FROM module_reroll_candidates WHERE module_id = ?", (self.module_id,)).fetchone()["id"])
        result = client.get(f"/modules/reroll/result/{candidate_id}")
        self.assertEqual(result.status_code, 200)
        accepted = client.post("/modules/reroll/accept", data={"candidate_id": candidate_id}, follow_redirects=True)
        self.assertEqual(accepted.status_code, 200)
        self.assertIn("採用しました", accepted.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()

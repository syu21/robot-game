import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class LabMiniTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True
        game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = False

        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected, coins)
                VALUES (?, ?, ?, 0, 0, 100)
                """,
                ("mini_user", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("mini_user",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.user_id)
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected, coins)
                VALUES (?, ?, ?, 1, 1, 100)
                """,
                ("mini_admin", "x", now),
            )
            self.admin_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("mini_admin",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.admin_id)
            db.commit()

    def tearDown(self):
        game_app.app.config.pop("BYPASS_RELEASE_GATES_IN_TESTS", None)
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self, *, admin=False):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.admin_id if admin else self.user_id
            session["username"] = "mini_admin" if admin else "mini_user"
        return client

    def _mini_robot(self, user_id):
        db = game_app.get_db()
        return db.execute("SELECT * FROM user_mini_robots WHERE user_id = ?", (int(user_id),)).fetchone()

    def _select_mini_robot(self, client, species_key="cerberus"):
        return client.post("/lab/mini/select", data={"species_key": species_key}, follow_redirects=True)

    def test_species_definitions_and_safe_lines(self):
        for key in ("cerberus", "phoenix", "hydra"):
            self.assertIn(key, game_app.MINI_ROBOT_SPECIES_META)
            self.assertIn(key, game_app.MINI_ROBOT_EVOLUTION_SEEDS)
            for state in ("normal", "blink", "happy", "sleep"):
                self.assertIn(state, game_app.MINI_ROBOT_STATE_LABELS)
                self.assertEqual(game_app._mini_robot_image_rel(key, state), f"mini_robots/{key}/{state}.png")

        ng_words = ("嫌", "怒", "悲", "無視", "警戒", "不満", "失敗", "寂し", "下がった")
        lines = []
        for species_lines in game_app.MINI_ROBOT_CARE_LINES.values():
            lines.extend(species_lines)
        lines.extend(game_app.COMMON_MINI_ROBOT_CARE_LINES)
        for line in lines:
            self.assertFalse(any(word in line for word in ng_words), line)

    def test_create_sets_internal_fields_and_audit(self):
        client = self._client(admin=True)
        resp = client.get("/lab/mini")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("最初のミニロボを選ぶ", html)
        self.assertIn("フェニックス", html)
        self.assertIn("ヒュドラ", html)

        resp = self._select_mini_robot(client, "phoenix")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("管理者メモ", resp.get_data(as_text=True))

        with game_app.app.app_context():
            db = game_app.get_db()
            robot = self._mini_robot(self.admin_id)
            self.assertEqual(robot["species_key"], "phoenix")
            self.assertIn(robot["personality_key"], game_app.MINI_ROBOT_PERSONALITY_KEYS)
            self.assertIn(robot["growth_type"], game_app.MINI_ROBOT_GROWTH_TYPES)
            self.assertGreater(int(robot["behavior_seed"]), 0)
            self.assertIn(robot["evolution_seed"], game_app.MINI_ROBOT_EVOLUTION_SEEDS["phoenix"])
            self.assertIn(robot["favorite_time_band"], game_app.MINI_ROBOT_TIME_BANDS)
            self.assertEqual(robot["last_state_reason"], "created")
            audit = db.execute(
                "SELECT payload_json FROM world_events_log WHERE event_type = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
                (game_app.AUDIT_EVENT_TYPES["LAB_MINI_CREATE"], self.admin_id),
            ).fetchone()
            payload = json.loads(audit["payload_json"])
            self.assertEqual(payload["mini_robot_id"], robot["id"])
            self.assertIn("personality_key", payload)

    def test_care_once_updates_internal_values_and_second_does_not(self):
        client = self._client(admin=True)
        self._select_mini_robot(client, "cerberus")
        with game_app.app.app_context():
            db = game_app.get_db()
            robot = self._mini_robot(self.admin_id)
            db.execute(
                "UPDATE user_mini_robots SET personality_key = 'curious', trust = 0, curiosity = 0, care_count = 0 WHERE id = ?",
                (int(robot["id"]),),
            )
            db.commit()

        first = client.post("/lab/mini/care", data={"action_key": "pet"}, follow_redirects=True)
        self.assertEqual(first.status_code, 200)
        self.assertIn("ごきげん", first.get_data(as_text=True))
        with game_app.app.app_context():
            db = game_app.get_db()
            after = self._mini_robot(self.admin_id)
            self.assertEqual(int(after["care_count"]), 1)
            self.assertEqual(int(after["consecutive_care_days"]), 1)
            self.assertGreaterEqual(int(after["trust"]), 1)
            self.assertEqual(int(after["curiosity"]), 1)
            self.assertEqual(after["current_state"], "happy")
            self.assertEqual(after["last_state_reason"], "after_care")
            snapshot = {key: after[key] for key in after.keys()}

        second = client.post("/lab/mini/care", data={"action_key": "energy"}, follow_redirects=True)
        self.assertEqual(second.status_code, 200)
        self.assertIn("今日はもうお世話済みです", second.get_data(as_text=True))
        with game_app.app.app_context():
            after_second_row = self._mini_robot(self.admin_id)
            after_second = {key: after_second_row[key] for key in after_second_row.keys()}
            self.assertEqual(after_second["care_count"], snapshot["care_count"])
            self.assertEqual(after_second["trust"], snapshot["trust"])
            self.assertEqual(after_second["growth_exp"], snapshot["growth_exp"])

    def test_observe_logs_once_per_time_band_without_rewards(self):
        client = self._client(admin=True)
        self._select_mini_robot(client, "cerberus")
        with game_app.app.app_context():
            db = game_app.get_db()
            before_user = db.execute("SELECT coins FROM users WHERE id = ?", (self.admin_id,)).fetchone()
            before_robot = self._mini_robot(self.admin_id)
            before_part_count = db.execute("SELECT COUNT(*) AS c FROM part_instances WHERE user_id = ?", (self.admin_id,)).fetchone()["c"]

        first = client.post("/lab/mini/observe", follow_redirects=True)
        self.assertEqual(first.status_code, 200)
        self.assertIn("ケルベロス", first.get_data(as_text=True))
        second = client.post("/lab/mini/observe", follow_redirects=True)
        self.assertEqual(second.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            after_user = db.execute("SELECT coins FROM users WHERE id = ?", (self.admin_id,)).fetchone()
            after_robot = self._mini_robot(self.admin_id)
            after_part_count = db.execute("SELECT COUNT(*) AS c FROM part_instances WHERE user_id = ?", (self.admin_id,)).fetchone()["c"]
            observe_logs = db.execute(
                "SELECT COUNT(*) AS c FROM mini_robot_logs WHERE mini_robot_id = ? AND event_type = 'observe'",
                (int(after_robot["id"]),),
            ).fetchone()["c"]
            self.assertEqual(int(observe_logs), 1)
            self.assertEqual(after_user["coins"], before_user["coins"])
            self.assertEqual(int(after_part_count), int(before_part_count))
            self.assertEqual(after_robot["affection"], before_robot["affection"])
            self.assertEqual(after_robot["energy"], before_robot["energy"])
            self.assertEqual(after_robot["trust"], before_robot["trust"])
            self.assertEqual(after_robot["growth_exp"], before_robot["growth_exp"])

    def test_rename_rejects_too_long_name(self):
        client = self._client(admin=True)
        self._select_mini_robot(client, "cerberus")
        long_name = "あ" * 19
        resp = client.post("/lab/mini/rename", data={"nickname": long_name}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("名前は18文字までです", resp.get_data(as_text=True))

    def test_release_gate_controls_public_access(self):
        user_client = self._client()
        admin_client = self._client(admin=True)
        admin_client.post("/admin/release", data={"feature_key": "lab", "state": "public"}, follow_redirects=True)

        blocked = user_client.get("/lab/mini", follow_redirects=True)
        self.assertEqual(blocked.status_code, 200)
        self.assertIn("準備中", blocked.get_data(as_text=True))
        with game_app.app.app_context():
            self.assertIsNone(self._mini_robot(self.user_id))

        admin_client.post("/admin/release", data={"feature_key": "lab_mini", "state": "public"}, follow_redirects=True)
        visible = user_client.get("/lab/mini")
        self.assertEqual(visible.status_code, 200)
        self.assertIn("ミニロボ培養室", visible.get_data(as_text=True))
        self.assertIn("最初のミニロボを選ぶ", visible.get_data(as_text=True))
        self.assertNotIn("管理者メモ", visible.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()

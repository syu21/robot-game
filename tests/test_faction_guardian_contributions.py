import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactionGuardianContributionTests(unittest.TestCase):
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
            self.admin_id = self._create_user(db, "guardian_admin2", now, "aurix", is_admin=1)
            self.aurix_user = self._create_user(db, "aurix_alpha", now, "aurix")
            self.aurix_user_b = self._create_user(db, "aurix_beta", now, "aurix")
            self.aurix_user_c = self._create_user(db, "aurix_gamma", now, "aurix")
            self.ignis_user = self._create_user(db, "ignis_alpha", now, "ignis")
            self.ventra_user = self._create_user(db, "ventra_alpha", now, "ventra")
            self.week_key = game_app.get_current_week_key()
            self.guardian_ids = {}
            for faction_key, title in (("aurix", "Aurix Guard"), ("ignis", "Ignis Guard"), ("ventra", "Ventra Guard")):
                submission_id = self._create_submission(db, self.admin_id, title, now)
                row = game_app.set_faction_guardian_from_submission(db, self.week_key, faction_key, submission_id)
                self.guardian_ids[faction_key] = int(row["id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _create_user(self, db, username, now, faction, *, is_admin=0, display_name=None):
        db.execute(
            """
            INSERT INTO users (username, display_name, password_hash, created_at, is_admin, wins, max_unlocked_layer, faction)
            VALUES (?, ?, ?, ?, ?, 0, 1, ?)
            """,
            (username, display_name, "x", now, int(is_admin), faction),
        )
        user_id = int(db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"])
        game_app.initialize_new_user(db, user_id)
        return user_id

    def _create_submission(self, db, user_id, title, now):
        cur = db.execute(
            """
            INSERT INTO lab_robot_submissions
            (user_id, title, comment, image_path, thumb_path, status, created_at, updated_at, approved_at, approved_by_user_id)
            VALUES (?, ?, 'comment', 'lab/submission.png', 'lab/submission_thumb.png', 'approved', ?, ?, ?, ?)
            """,
            (int(user_id), title, now, now, now, self.admin_id),
        )
        return int(cur.lastrowid)

    def _client(self, user_id=None, username="aurix_alpha"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id or self.aurix_user)
            session["username"] = username
        return client

    def _attack(self, db, user_id, attacker_faction, target_faction, event_type, damage):
        db.execute(
            """
            INSERT INTO faction_guardian_attacks
            (week_key, attacker_faction_key, target_faction_key, guardian_id, attacker_user_id,
             source_event_type, source_event_id, request_id, damage, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.week_key,
                attacker_faction,
                target_faction,
                self.guardian_ids[target_faction],
                int(user_id),
                event_type,
                int(time.time_ns() % 1000000000),
                f"req-{time.time_ns()}",
                int(damage),
                game_app.now_str(),
            ),
        )

    def test_user_contribution_is_aggregated_with_breakdown(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._attack(db, self.aurix_user, "aurix", "ignis", game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], 1)
            self._attack(db, self.aurix_user, "aurix", "ignis", game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], 30)
            self._attack(db, self.aurix_user, "aurix", "ignis", game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"], 15)
            result = game_app.get_user_guardian_contribution(db, self.aurix_user, self.week_key)
            self.assertEqual(result["total_damage"], 46)
            self.assertEqual(result["explore_damage"], 1)
            self.assertEqual(result["boss_damage"], 30)
            self.assertEqual(result["evolve_damage"], 15)
            self.assertEqual(result["tower_damage"], 0)

    def test_faction_ranking_orders_by_total_damage(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._attack(db, self.aurix_user, "aurix", "ignis", game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], 1)
            self._attack(db, self.aurix_user_b, "aurix", "ignis", game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], 30)
            self._attack(db, self.aurix_user_c, "aurix", "ignis", game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"], 15)
            rows = game_app.get_faction_guardian_contribution_ranking(db, "aurix", self.week_key, limit=5)
            self.assertEqual([row["user_id"] for row in rows], [self.aurix_user_b, self.aurix_user_c, self.aurix_user])
            self.assertEqual(rows[0]["label"], "守護戦主力")

    def test_faction_page_shows_contribution_ranking_and_related_logs_only(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._attack(db, self.aurix_user, "aurix", "ignis", game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], 30)
            self._attack(db, self.ignis_user, "ignis", "aurix", game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"], 15)
            self._attack(db, self.ignis_user, "ignis", "ventra", game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], 30)
            db.commit()
        html = self._client().get("/faction").get_data(as_text=True)
        self.assertIn("あなたの今週の守護戦貢献", html)
        self.assertIn("合計研究ダメージ: 30", html)
        self.assertIn("今週の守護戦貢献者", html)
        self.assertIn("aurix_alpha", html)
        self.assertIn("陣営守護戦ログ", html)
        self.assertIn("Ignis Guard", html)
        self.assertIn("Aurix Guard", html)
        self.assertNotIn("イグニス研究員 ignis_alpha が、ヴェントラ守護機", html)

    def test_world_shows_only_large_guardian_highlights(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._attack(db, self.aurix_user, "aurix", "ignis", game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], 1)
            self._attack(db, self.aurix_user_b, "aurix", "ignis", game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], 30)
            db.commit()
        html = self._client().get("/world").get_data(as_text=True)
        self.assertIn("守護戦ハイライト", html)
        self.assertIn("aurix_beta", html)
        self.assertIn("30研究ダメージ", html)
        self.assertNotIn("aurix_alpha が、", html)
        self.assertNotIn("1研究ダメージ", html)

    def test_comms_faction_shows_guardian_progress(self):
        client = self._client()
        html = client.get("/comms/faction").get_data(as_text=True)
        self.assertIn("今週の陣営守護戦", html)
        self.assertIn("自陣営守護機", html)
        self.assertIn("攻略対象", html)
        self.assertIn("防衛率", html)
        self.assertIn("解析率", html)

    def test_unset_guardian_pages_do_not_500(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("DELETE FROM faction_guardian_attacks")
            db.execute("DELETE FROM faction_guardians")
            db.commit()
        client = self._client()
        self.assertEqual(client.get("/faction").status_code, 200)
        self.assertEqual(client.get("/world").status_code, 200)
        resp = client.get("/comms/faction")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("今週の守護機はまだ設定されていません", resp.get_data(as_text=True))

    def test_guardian_log_html_is_escaped(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET display_name = ? WHERE id = ?", ("<script>x</script>", self.aurix_user))
            db.execute("UPDATE faction_guardians SET guardian_name = ? WHERE faction_key = 'ignis'", ("<b>Ignis</b>",))
            self._attack(db, self.aurix_user, "aurix", "ignis", game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], 30)
            db.commit()
        html = self._client().get("/faction").get_data(as_text=True)
        self.assertNotIn("<script>x</script>", html)
        self.assertNotIn("<b>Ignis</b>", html)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", html)
        self.assertIn("&lt;b&gt;Ignis&lt;/b&gt;", html)


if __name__ == "__main__":
    unittest.main()

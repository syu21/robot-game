import json
import os
import tempfile
import time
import unittest
from unittest import mock

import app as game_app
import init_db
from services.stats import compute_part_stats, compute_robot_stats


class DinosaurAdminSeriesTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, coins, max_unlocked_layer)
                VALUES (?, ?, ?, 1, 0, 0, 5)
                """,
                ("dino_admin", "x", now),
            )
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, coins, max_unlocked_layer)
                VALUES (?, ?, ?, 0, 0, 0, 5)
                """,
                ("dino_user", "x", now),
            )
            self.admin_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("dino_admin",)).fetchone()["id"])
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("dino_user",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.admin_id)
            game_app.initialize_new_user(db, self.user_id)
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self, user_id=None, username="dino_admin"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id or self.admin_id)
            session["username"] = username
        return client

    def test_dinosaur_n_parts_seeded_as_public_n_parts(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            rows = db.execute(
                """
                SELECT key, part_type, image_path, rarity, series, frame_type, is_admin_only, display_name_ja
                FROM robot_parts
                WHERE series LIKE 'dino_%'
                ORDER BY key ASC
                """
            ).fetchall()
            self.assertEqual(len(rows), 28)
            self.assertEqual({row["part_type"] for row in rows}, {"HEAD", "RIGHT_ARM", "LEFT_ARM", "LEGS"})
            self.assertEqual({row["rarity"] for row in rows}, {"N"})
            for row in rows:
                self.assertEqual(row["frame_type"], "dinosaur")
                self.assertEqual(int(row["is_admin_only"]), 0)
                self.assertTrue(str(row["key"]).startswith(("head_n_dino_", "right_arm_n_dino_", "left_arm_n_dino_", "legs_n_dino_")))
                self.assertEqual(row["image_path"], f"parts/dinosaur/{row['key']}.png")
                self.assertTrue(str(row["display_name_ja"]).strip())
                stats = game_app.DINO_PART_STAT_BY_KEY[row["key"]]
                self.assertEqual(sum(int(value) for value in stats.values()), 12)
                self.assertTrue(all(int(value) >= 1 for value in stats.values()))
                resolved_rel = game_app._part_image_rel(row)
                self.assertNotEqual(resolved_rel, "enemies/_placeholder.png")
                self.assertTrue(os.path.exists(os.path.join(game_app.STATIC_ROOT, resolved_rel)), resolved_rel)

            series_rows = db.execute(
                """
                SELECT series_key, frame_type, max_rarity, can_evolve, is_active
                FROM series_master
                WHERE series_key LIKE 'dino_%'
                """
            ).fetchall()
            self.assertEqual(len(series_rows), 7)
            for row in series_rows:
                self.assertEqual(row["frame_type"], "dinosaur")
                self.assertEqual(row["max_rarity"], "N")
                self.assertEqual(int(row["can_evolve"]), 0)
                self.assertEqual(int(row["is_active"]), 1)

    def test_normal_user_starts_without_dinosaur_parts(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(
                db.execute(
                    """
                    SELECT COUNT(*) AS c
                    FROM part_instances pi
                    JOIN robot_parts rp ON rp.id = pi.part_id
                    WHERE pi.user_id = ? AND rp.series LIKE 'dino_%'
                    """,
                    (self.user_id,),
                ).fetchone()["c"]
            )
            self.assertEqual(count, 0)

    def test_dinosaur_campaign_adds_public_n_drop_on_win_reward(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            with mock.patch.object(game_app.random, "random", side_effect=[1.0, 0.0]):
                rewards = game_app._roll_battle_rewards(
                    db,
                    self.user_id,
                    1,
                    area_key="layer_1",
                )
            self.assertTrue(rewards["campaign_drop_triggered"])
            self.assertEqual(len(rewards["dropped_parts"]), 1)
            dropped = rewards["dropped_parts"][0]
            self.assertEqual(dropped["source"], "campaign")
            self.assertEqual(dropped["campaign_key"], game_app.DINOSAUR_DEBUT_CAMPAIGN["key"])
            self.assertEqual(dropped["drop_type"], "campaign_dinosaur_debut")
            part = game_app._get_part_by_key(db, dropped["part_key"])
            self.assertEqual(part["frame_type"], "dinosaur")
            self.assertEqual(part["rarity"], "N")

    def test_dinosaur_parts_are_excluded_from_base_n_drops(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE robot_parts SET is_active = 0 WHERE series NOT LIKE 'dino_%'")
            db.commit()
            dropped = game_app._pick_drop_part_master(db, rarity="N", area_key="layer_1", user_id=self.user_id)
            self.assertIsNone(dropped)

    def test_dinosaur_campaign_does_not_add_drop_outside_target_area(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            with mock.patch.object(game_app.random, "random", side_effect=[1.0]):
                rewards = game_app._roll_battle_rewards(
                    db,
                    self.user_id,
                    1,
                    area_key="layer_5_final",
                )
            self.assertFalse(rewards["campaign_drop_triggered"])
            self.assertEqual(rewards["dropped_parts"], [])

    def test_dinosaur_r_parts_are_not_r_drop_candidates(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            base = db.execute("SELECT * FROM robot_parts WHERE key = ?", ("head_n_dino_tyranno",)).fetchone()
            db.execute("UPDATE robot_parts SET is_active = 0")
            db.execute(
                """
                INSERT INTO robot_parts (
                    part_type, key, image_path, rarity, element, series, frame_type,
                    series_key, series_label, display_name_ja, is_active, is_unlocked,
                    is_admin_only, created_at
                )
                VALUES ('HEAD', 'head_r_dino_tyranno', ?, 'R', 'NORMAL', 'dino_tyranno', 'dinosaur',
                        'dino_tyranno', 'ティラノ', 'ティラノRテスト', 1, 1, 0, ?)
                """,
                (base["image_path"], now),
            )
            db.commit()
            dropped = game_app._pick_drop_part_master(db, rarity="R", area_key="layer_5_pinnacle", user_id=self.user_id)
            self.assertIsNone(dropped)

    def test_home_shows_dinosaur_campaign_not_old_insect_campaign(self):
        client = self._client(user_id=self.user_id, username="dino_user")
        html = client.get("/home").get_data(as_text=True)
        self.assertIn("恐竜発掘キャンペーン", html)
        self.assertIn("出撃で恐竜型パーツを発見できることがあります", html)
        self.assertNotIn("虫型研究 進行中", html)

    def test_admin_grant_route_adds_missing_only_and_writes_audit(self):
        client = self._client()
        res = client.post("/admin/parts/grant-dinosaur-n", follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        with game_app.app.app_context():
            db = game_app.ge
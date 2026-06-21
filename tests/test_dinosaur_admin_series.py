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
            db = game_app.get_db()
            count = int(
                db.execute(
                    """
                    SELECT COUNT(*) AS c
                    FROM part_instances pi
                    JOIN robot_parts rp ON rp.id = pi.part_id
                    WHERE pi.user_id = ? AND rp.series LIKE 'dino_%'
                    """,
                    (self.admin_id,),
                ).fetchone()["c"]
            )
            self.assertEqual(count, 28)

        res = client.post("/admin/parts/grant-dinosaur-n", follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            count_after = int(
                db.execute(
                    """
                    SELECT COUNT(*) AS c
                    FROM part_instances pi
                    JOIN robot_parts rp ON rp.id = pi.part_id
                    WHERE pi.user_id = ? AND rp.series LIKE 'dino_%'
                    """,
                    (self.admin_id,),
                ).fetchone()["c"]
            )
            self.assertEqual(count_after, 28)
            audit = db.execute(
                """
                SELECT payload_json
                FROM world_events_log
                WHERE user_id = ? AND event_type = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (self.admin_id, game_app.AUDIT_EVENT_TYPES["INVENTORY_DELTA"]),
            ).fetchone()
            payload = json.loads(audit["payload_json"])
            self.assertEqual(payload["reason"], "admin_grant_dinosaur_n_series")
            self.assertEqual(payload["granted_count"], 0)
            self.assertEqual(payload["skipped_count"], 28)

    def test_dinosaur_fixed_stats_and_flat_series_bonus(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            part_keys = ("head_n_dino_tyranno", "right_arm_n_dino_tyranno", "left_arm_n_dino_tyranno", "legs_n_dino_tyranno")
            instance_ids = []
            for part_key in part_keys:
                part = db.execute("SELECT * FROM robot_parts WHERE key = ?", (part_key,)).fetchone()
                instance_ids.append(game_app._create_part_instance_from_master(db, self.admin_id, part, plus=0))
            db.commit()
            rows = db.execute(
                """
                SELECT pi.*, rp.key AS master_key
                FROM part_instances pi
                JOIN robot_parts rp ON rp.id = pi.part_id
                WHERE pi.id IN ({})
                ORDER BY rp.key ASC
                """.format(",".join(["?"] * len(instance_ids))),
                tuple(instance_ids),
            ).fetchall()
            parts = [dict(row) for row in rows]
            for part in parts:
                expected = game_app.DINO_PART_STAT_BY_KEY[part["master_key"]]
                actual = compute_part_stats(part)
                for stat_key, unique_value in expected.items():
                    common_bonus = 2 if stat_key == "hp" else 1
                    self.assertEqual(actual[stat_key], unique_value + common_bonus)

            base = compute_robot_stats(parts, series_bonus_defs={}, series_progress_layer=1)["stats"]
            with_bonus = compute_robot_stats(
                parts,
                series_bonus_defs=game_app._load_series_bonus_defs(db, active_only=True),
                series_progress_layer=1,
            )
            self.assertEqual(with_bonus["stats"]["atk"], base["atk"] + 2)
            self.assertEqual(with_bonus["stats"]["cri"], base["cri"] + 1)
            self.assertTrue(all(row["value_type"] == "flat" for row in with_bonus["series_bonus"]))

    def test_dinosaur_loadout_generates_composed_image_and_icon(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            robot_id = int(
                db.execute("SELECT active_robot_id FROM users WHERE id = ?", (self.admin_id,)).fetchone()["active_robot_id"]
            )
            instance_ids = {}
            for slot, part_key in {
                "head": "head_n_dino_spino",
                "r_arm": "right_arm_n_dino_spino",
                "l_arm": "left_arm_n_dino_spino",
                "legs": "legs_n_dino_spino",
            }.items():
                part = db.execute("SELECT * FROM robot_parts WHERE key = ?", (part_key,)).fetchone()
                instance_ids[slot] = game_app._create_part_instance_from_master(db, self.admin_id, part, plus=0, status="equipped")
            db.execute(
                """
                UPDATE robot_instance_parts
                SET head_key = ?,
                    r_arm_key = ?,
                    l_arm_key = ?,
                    legs_key = ?,
                    head_part_instance_id = ?,
                    r_arm_part_instance_id = ?,
                    l_arm_part_instance_id = ?,
                    legs_part_instance_id = ?
                WHERE robot_instance_id = ?
                """,
                (
                    "head_n_dino_spino",
                    "right_arm_n_dino_spino",
                    "left_arm_n_dino_spino",
                    "legs_n_dino_spino",
                    instance_ids["head"],
                    instance_ids["r_arm"],
                    instance_ids["l_arm"],
                    instance_ids["legs"],
                    robot_id,
                ),
            )
            robot = db.execute("SELECT * FROM robot_instance_parts WHERE robot_instance_id = ?", (robot_id,)).fetchone()
            rel_path = game_app._compose_instance_image(db, {"id": robot_id}, robot)
            self.assertTrue(rel_path)
            self.assertTrue(os.path.exists(os.path.join(game_app.STATIC_ROOT, rel_path)))
            icon_row = db.execute("SELECT icon_32_path FROM robot_instances WHERE id = ?", (robot_id,)).fetchone()
            self.assertTrue(icon_row["icon_32_path"])
            self.assertTrue(os.path.exists(os.path.join(game_app.STATIC_ROOT, icon_row["icon_32_path"])))


if __name__ == "__main__":
    unittest.main()

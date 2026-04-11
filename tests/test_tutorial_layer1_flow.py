import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class TutorialLayer1FlowTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 0, 0, 1000, 1)
                """,
                ("tutorial_l1", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("tutorial_l1",),
            ).fetchone()["id"]
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (self.user_id, "FirstRunner", now, now),
            )
            self.robot_id = db.execute(
                "SELECT id FROM robot_instances WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (self.user_id,),
            ).fetchone()["id"]

            def pick_key(part_type):
                row = db.execute(
                    "SELECT key FROM robot_parts WHERE part_type = ? AND is_active = 1 ORDER BY id ASC LIMIT 1",
                    (part_type,),
                ).fetchone()
                self.assertIsNotNone(row)
                return row["key"]

            db.execute(
                """
                INSERT INTO robot_instance_parts (robot_instance_id, head_key, r_arm_key, l_arm_key, legs_key)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self.robot_id,
                    pick_key("HEAD"),
                    pick_key("RIGHT_ARM"),
                    pick_key("LEFT_ARM"),
                    pick_key("LEGS"),
                ),
            )
            db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (self.robot_id, self.user_id))
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    @staticmethod
    def _stable_weekly_env():
        return {
            "element": "NORMAL",
            "mode": "安定",
            "enemy_spawn_bonus": 0.0,
            "drop_bonus": 0.0,
            "reason": "test",
        }

    @staticmethod
    def _resolve_player_win(att_atk, att_acc, att_cri, def_def, def_acc, **kwargs):
        if kwargs.get("attacker_archetype") is not None:
            return 999, False
        return 0, False

    @staticmethod
    def _resolve_player_loss(att_atk, att_acc, att_cri, def_def, def_acc, **kwargs):
        if kwargs.get("attacker_archetype") is not None:
            return 0, False
        return 999, False

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "tutorial_l1"
        return client

    def _explore(self, resolver):
        client = self._client()
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "_enforce_explore_cooldown_or_wait", return_value=0
        ), patch.object(game_app, "resolve_attack", side_effect=resolver):
            return client.post("/explore", data={"area_key": "layer_1"})

    def _user_tutorial_row(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            return db.execute(
                """
                SELECT tutorial_layer1_state, tutorial_layer1_normal_win_count,
                       tutorial_layer1_boss_seen_at, tutorial_layer1_boss_fail_count,
                       tutorial_layer1_forced_boss_ready, tutorial_layer1_fuse_after_boss_fail_count,
                       max_unlocked_layer
                FROM users
                WHERE id = ?
                """,
                (self.user_id,),
            ).fetchone()

    def _insert_strengthen_materials(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            part = db.execute(
                """
                SELECT id, part_type
                FROM robot_parts
                WHERE part_type = 'HEAD' AND is_active = 1
                ORDER BY id ASC
                LIMIT 1
                """
            ).fetchone()
            self.assertIsNotNone(part)
            ids = []
            for _ in range(3):
                cur = db.execute(
                    """
                    INSERT INTO part_instances
                    (part_id, user_id, part_type, rarity, element, series, plus,
                     w_hp, w_atk, w_def, w_spd, w_acc, w_cri, status, created_at)
                    VALUES (?, ?, ?, 'N', 'NORMAL', 'starter', 0, 1, 1, 1, 1, 1, 1, 'inventory', ?)
                    """,
                    (int(part["id"]), self.user_id, part["part_type"], now),
                )
                ids.append(int(cur.lastrowid))
            db.commit()
            return ids

    def test_normal_win_forces_boss_then_failed_boss_guides_strengthen(self):
        first = self._explore(self._resolve_player_win)
        self.assertEqual(first.status_code, 200)
        row = self._user_tutorial_row()
        self.assertEqual(row["tutorial_layer1_state"], game_app.TUTORIAL_LAYER1_STATE_WON_NORMAL_ONCE)
        self.assertEqual(int(row["tutorial_layer1_normal_win_count"]), 1)
        self.assertEqual(int(row["tutorial_layer1_forced_boss_ready"]), 1)

        boss = self._explore(self._resolve_player_loss)
        self.assertEqual(boss.status_code, 200)
        html = boss.get_data(as_text=True)
        self.assertIn("第1層ボスの圧力", html)
        self.assertIn("パーツ強化へ", html)
        row = self._user_tutorial_row()
        self.assertEqual(row["tutorial_layer1_state"], game_app.TUTORIAL_LAYER1_STATE_BOSS_FAILED_ONCE)
        self.assertGreater(int(row["tutorial_layer1_boss_seen_at"] or 0), 0)
        self.assertEqual(int(row["tutorial_layer1_boss_fail_count"]), 1)
        self.assertEqual(int(row["tutorial_layer1_forced_boss_ready"]), 0)

        home = self._client().get("/home")
        self.assertEqual(home.status_code, 200)
        home_html = home.get_data(as_text=True)
        self.assertIn("強化して再挑戦", home_html)
        self.assertIn("1回強化するだけでも突破率が上がります", home_html)

    def test_fuse_after_boss_fail_guarantees_retry_and_clear(self):
        self._explore(self._resolve_player_win)
        self._explore(self._resolve_player_loss)
        ids = self._insert_strengthen_materials()

        client = self._client()
        fuse_resp = client.post(
            "/parts/strengthen",
            data={"mode": "select", "base_id": str(ids[0])},
            follow_redirects=False,
        )
        self.assertEqual(fuse_resp.status_code, 302)
        row = self._user_tutorial_row()
        self.assertEqual(row["tutorial_layer1_state"], game_app.TUTORIAL_LAYER1_STATE_BOSS_FAILED_ONCE)
        self.assertEqual(int(row["tutorial_layer1_forced_boss_ready"]), 1)
        self.assertEqual(int(row["tutorial_layer1_fuse_after_boss_fail_count"]), 1)

        retry = self._explore(self._resolve_player_win)
        self.assertEqual(retry.status_code, 200)
        html = retry.get_data(as_text=True)
        self.assertIn("第1層突破", html)
        row = self._user_tutorial_row()
        self.assertEqual(row["tutorial_layer1_state"], game_app.TUTORIAL_LAYER1_STATE_CLEARED)
        self.assertEqual(int(row["max_unlocked_layer"]), 2)

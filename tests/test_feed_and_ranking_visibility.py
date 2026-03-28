import json
import os
import re
import tempfile
import time
import unittest

import app as game_app
import init_db


class FeedAndRankingVisibilityTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 1, 0, 1)
                """,
                ("feed_rank_user", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("feed_rank_user",),
            ).fetchone()["id"]
            game_app.initialize_new_user(db, self.user_id)
            self.robot_id = db.execute(
                "SELECT active_robot_id FROM users WHERE id = ?",
                (self.user_id,),
            ).fetchone()["active_robot_id"]
            target_part = db.execute(
                """
                SELECT key, display_name_ja, part_type
                FROM robot_parts
                WHERE is_active = 1
                ORDER BY id ASC
                LIMIT 1
                """
            ).fetchone()
            self.target_part_key = target_part["key"]
            self.target_part_name = target_part["display_name_ja"] or target_part["key"]
            self.target_part_type = target_part["part_type"]
            boss = db.execute(
                "SELECT id, key, name_ja FROM enemies WHERE key = ?",
                ("boss_ignis_reaver",),
            ).fetchone()
            self.boss_id = boss["id"]
            self.boss_key = boss["key"]
            self.boss_name = boss["name_ja"]
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "feed_rank_user"
        return client

    def test_feed_shows_public_boss_and_evolve_events(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO world_events_log
                (created_at, event_type, payload_json, user_id, entity_type, entity_id)
                VALUES (?, ?, ?, ?, 'enemy', ?)
                """,
                (
                    now,
                    game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                    json.dumps(
                        {
                            "week_key": game_app._world_week_key(),
                            "area_key": "layer_3",
                            "area_label": "第三層",
                            "enemy_key": self.boss_key,
                            "enemy_name": self.boss_name,
                            "robot_instance_id": int(self.robot_id),
                            "robot_name": "GuideBot",
                        },
                        ensure_ascii=False,
                    ),
                    self.user_id,
                    int(self.boss_id),
                ),
            )
            db.execute(
                """
                INSERT INTO world_events_log
                (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    now + 1,
                    game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"],
                    json.dumps(
                        {
                            "part_type": self.target_part_type,
                            "target_part_key": self.target_part_key,
                            "target_part_name": self.target_part_name,
                        },
                        ensure_ascii=False,
                    ),
                    self.user_id,
                ),
            )
            db.commit()

        client = self._client()
        resp = client.get("/feed")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("BOSS DEFEATED", html)
        self.assertIn("ボス撃破:", html)
        self.assertIn("feed_rank_user", html)
        self.assertIn(self.boss_name, html)
        self.assertIn("戦域: 第三層", html)
        self.assertIn("進化成功", html)
        self.assertIn("進化成功:", html)
        self.assertIn(self.target_part_name, html)
        self.assertIn("部位:", html)

    def test_feed_supports_boss_and_evolve_filters(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO world_events_log
                (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    now,
                    game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                    json.dumps({"enemy_name": self.boss_name}, ensure_ascii=False),
                    self.user_id,
                ),
            )
            db.execute(
                """
                INSERT INTO world_events_log
                (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    now + 1,
                    game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"],
                    json.dumps({"target_part_name": self.target_part_name}, ensure_ascii=False),
                    self.user_id,
                ),
            )
            db.commit()

        client = self._client()
        boss_resp = client.get("/feed?type=boss")
        self.assertEqual(boss_resp.status_code, 200)
        boss_html = boss_resp.get_data(as_text=True)
        self.assertIn(self.boss_name, boss_html)
        self.assertNotIn(self.target_part_name, boss_html)

        evolve_resp = client.get("/feed?type=evolve")
        self.assertEqual(evolve_resp.status_code, 200)
        evolve_html = evolve_resp.get_data(as_text=True)
        self.assertIn(self.target_part_name, evolve_html)
        self.assertNotIn(self.boss_name, evolve_html)

    def test_feed_weekly_filter_shows_faction_and_research_events(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            week_key = game_app._world_week_key()
            db.execute(
                """
                INSERT INTO world_events_log
                (created_at, event_type, payload_json)
                VALUES (?, 'FACTION_WAR_RESULT', ?)
                """,
                (
                    now,
                    json.dumps(
                        {
                            "week_key": week_key,
                            "winner_faction": "ignis",
                            "scores": {"ignis": 120, "ventra": 95, "aurix": 80},
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            db.execute(
                """
                INSERT INTO world_events_log
                (created_at, event_type, payload_json)
                VALUES (?, 'RESEARCH_UNLOCK', ?)
                """,
                (
                    now + 1,
                    json.dumps(
                        {
                            "week_key": week_key,
                            "element": "FIRE",
                            "part_type": "HEAD",
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            db.commit()

        client = self._client()
        resp = client.get("/feed?type=weekly")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("陣営戦決着", html)
        self.assertIn("研究解禁", html)
        self.assertIn("IGNIS", html)
        self.assertIn("頭冠", html)


class RankingVisibilityTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 1, 5, 1)
                """,
                ("rank_alpha", "x", now),
            )
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 1, 2, 1)
                """,
                ("rank_beta", "x", now),
            )
            self.alpha_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("rank_alpha",),
            ).fetchone()["id"]
            self.beta_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("rank_beta",),
            ).fetchone()["id"]
            game_app.initialize_new_user(db, self.alpha_id)
            game_app.initialize_new_user(db, self.beta_id)
            self.alpha_robot_id = db.execute(
                "SELECT active_robot_id FROM users WHERE id = ?",
                (self.alpha_id,),
            ).fetchone()["active_robot_id"]
            self.beta_robot_id = db.execute(
                "SELECT active_robot_id FROM users WHERE id = ?",
                (self.beta_id,),
            ).fetchone()["active_robot_id"]

            week_key = game_app._world_week_key()
            start_dt, end_dt = game_app._world_week_bounds(week_key)
            current_ts = int(start_dt.timestamp()) + 3600
            prev_ts = int(start_dt.timestamp()) - 3600

            for offset in range(4):
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                    VALUES (?, ?, '{}', ?)
                    """,
                    (
                        current_ts if offset == 0 else (prev_ts - offset),
                        game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                        self.alpha_id,
                    ),
                )
            for offset in range(3):
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                    VALUES (?, ?, '{}', ?)
                    """,
                    (
                        current_ts + offset if offset < 2 else prev_ts - 10,
                        game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                        self.beta_id,
                    ),
                )
            for offset in range(2):
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                    VALUES (?, ?, '{}', ?)
                    """,
                    (
                        current_ts + 100 + offset,
                        game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                        self.beta_id,
                    ),
                )
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.alpha_id
            session["username"] = "rank_alpha"
        return client

    def _set_robot_weights(self, robot_id, *, name, hp, atk, defe, spd, acc, cri):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE robot_instances SET name = ? WHERE id = ?", (name, int(robot_id)))
            parts = db.execute(
                """
                SELECT head_part_instance_id, r_arm_part_instance_id, l_arm_part_instance_id, legs_part_instance_id
                FROM robot_instance_parts
                WHERE robot_instance_id = ?
                """,
                (int(robot_id),),
            ).fetchone()
            for part_instance_id in (
                int(parts["head_part_instance_id"]),
                int(parts["r_arm_part_instance_id"]),
                int(parts["l_arm_part_instance_id"]),
                int(parts["legs_part_instance_id"]),
            ):
                db.execute(
                    """
                    UPDATE part_instances
                    SET w_hp = ?, w_atk = ?, w_def = ?, w_spd = ?, w_acc = ?, w_cri = ?
                    WHERE id = ?
                    """,
                    (float(hp), float(atk), float(defe), float(spd), float(acc), float(cri), part_instance_id),
                )
            db.commit()

    def test_ranking_supports_explore_and_weekly_metrics(self):
        client = self._client()

        wins_resp = client.get("/ranking")
        self.assertEqual(wins_resp.status_code, 200)
        wins_html = wins_resp.get_data(as_text=True)
        self.assertIn("勝利数ランキング", wins_html)
        self.assertRegex(wins_html, re.compile(r"<td>1</td>.*?rank_alpha.*?<td>5</td>", re.S))

        explore_resp = client.get("/ranking?metric=explores")
        self.assertEqual(explore_resp.status_code, 200)
        explore_html = explore_resp.get_data(as_text=True)
        self.assertIn("探索数ランキング", explore_html)
        self.assertRegex(explore_html, re.compile(r"<td>1</td>.*?rank_alpha.*?<td>4</td>", re.S))

        weekly_explore_resp = client.get("/ranking?metric=weekly_explores")
        self.assertEqual(weekly_explore_resp.status_code, 200)
        weekly_explore_html = weekly_explore_resp.get_data(as_text=True)
        self.assertIn("今週探索数ランキング", weekly_explore_html)
        self.assertRegex(weekly_explore_html, re.compile(r"<td>1</td>.*?rank_beta.*?<td>2</td>", re.S))

        weekly_boss_resp = client.get("/ranking?metric=weekly_bosses")
        self.assertEqual(weekly_boss_resp.status_code, 200)
        weekly_boss_html = weekly_boss_resp.get_data(as_text=True)
        self.assertIn("今週ボス撃破ランキング", weekly_boss_html)
        self.assertRegex(weekly_boss_html, re.compile(r"<td>1</td>.*?rank_beta.*?<td>2</td>", re.S))

    def test_ranking_supports_robot_purpose_metrics(self):
        self._set_robot_weights(
            self.alpha_robot_id,
            name="Bulwark Alpha",
            hp=0.40,
            atk=0.04,
            defe=0.38,
            spd=0.06,
            acc=0.08,
            cri=0.04,
        )
        self._set_robot_weights(
            self.beta_robot_id,
            name="Swift Beta",
            hp=0.04,
            atk=0.12,
            defe=0.05,
            spd=0.58,
            acc=0.13,
            cri=0.08,
        )
        client = self._client()

        fastest_resp = client.get("/ranking?metric=fastest")
        self.assertEqual(fastest_resp.status_code, 200)
        fastest_html = fastest_resp.get_data(as_text=True)
        self.assertIn("最速ロボランキング", fastest_html)
        self.assertIn("Swift Beta", fastest_html)
        self.assertIn("Bulwark Alpha", fastest_html)
        self.assertIn("rank_beta", fastest_html)
        self.assertLess(fastest_html.index("Swift Beta"), fastest_html.index("Bulwark Alpha"))

        durable_resp = client.get("/ranking?metric=durable")
        self.assertEqual(durable_resp.status_code, 200)
        durable_html = durable_resp.get_data(as_text=True)
        self.assertIn("耐久ロボランキング", durable_html)
        self.assertIn("Bulwark Alpha", durable_html)
        self.assertIn("Swift Beta", durable_html)
        self.assertLess(durable_html.index("Bulwark Alpha"), durable_html.index("Swift Beta"))


if __name__ == "__main__":
    unittest.main()

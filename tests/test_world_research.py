import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class WorldResearchTests(unittest.TestCase):
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
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins, coins) VALUES (?, ?, ?, 1, 0, 0)",
                ("research_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("research_tester",),
            ).fetchone()["id"]
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _insert_locked_rare_part(self, db, key, part_type="HEAD", element="FIRE"):
        now = int(time.time())
        db.execute(
            """
            INSERT INTO robot_parts
            (part_type, key, image_path, rarity, element, series, offset_x, offset_y, is_active, is_unlocked, created_at)
            VALUES (?, ?, ?, 'R', ?, 'S1', 0, 0, 1, 0, ?)
            """,
            (part_type, key, "parts/head/1.png", element, now),
        )

    def test_locked_rare_part_never_drops(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._insert_locked_rare_part(db, "research_locked_fire_head")
            db.commit()

            dropped = game_app._add_part_drop(
                db,
                self.user_id,
                source="battle_drop",
                rarity="R",
                plus=0,
                as_instance=True,
            )
            self.assertIsNone(dropped)

            db.execute(
                "UPDATE robot_parts SET is_unlocked = 1 WHERE key = ?",
                ("research_locked_fire_head",),
            )
            db.commit()
            dropped2 = game_app._add_part_drop(
                db,
                self.user_id,
                source="battle_drop",
                rarity="R",
                plus=0,
                as_instance=True,
            )
            self.assertIsNotNone(dropped2)
            self.assertEqual(dropped2["part_key"], "research_locked_fire_head")

    def test_research_rollover_unlocks_stage_part(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._insert_locked_rare_part(db, "research_fire_head", part_type="HEAD", element="FIRE")
            game_app._ensure_world_research_rows(db)
            db.execute(
                "UPDATE world_research_progress SET progress = 50, unlocked_stage = 0 WHERE element = 'FIRE'"
            )
            now_week = game_app._world_week_key()
            target_start = game_app._world_week_bounds(now_week)[0] + game_app.timedelta(days=7)
            current_week = game_app._world_week_key(target_start.timestamp())
            prev_week = now_week
            db.execute(
                """
                INSERT INTO world_weekly_counters (week_key, metric_key, value)
                VALUES (?, 'kills_FIRE', 10)
                ON CONFLICT(week_key, metric_key) DO UPDATE SET value = excluded.value
                """,
                (prev_week,),
            )
            db.commit()

            result = game_app._advance_world_research(db, current_week)
            db.commit()

            self.assertEqual(result["winner_element"], "FIRE")
            self.assertTrue(result["unlocked"])
            row = db.execute(
                "SELECT progress, unlocked_stage FROM world_research_progress WHERE element = 'FIRE'"
            ).fetchone()
            self.assertEqual(int(row["progress"]), 0)
            self.assertEqual(int(row["unlocked_stage"]), 1)
            unlocked = db.execute(
                "SELECT is_unlocked FROM robot_parts WHERE key = 'research_fire_head'"
            ).fetchone()["is_unlocked"]
            self.assertEqual(int(unlocked), 1)
            event = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = 'RESEARCH_UNLOCK'"
            ).fetchone()["c"]
            self.assertEqual(int(event), 1)

    def test_research_advance_runs_once_per_week(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app._ensure_world_research_rows(db)
            db.execute(
                "UPDATE world_research_progress SET progress = 0, unlocked_stage = 0 WHERE element = 'FIRE'"
            )
            now_week = game_app._world_week_key()
            target_start = game_app._world_week_bounds(now_week)[0] + game_app.timedelta(days=7)
            current_week = game_app._world_week_key(target_start.timestamp())
            prev_week = now_week
            db.execute(
                """
                INSERT INTO world_weekly_counters (week_key, metric_key, value)
                VALUES (?, 'kills_FIRE', 10)
                ON CONFLICT(week_key, metric_key) DO UPDATE SET value = excluded.value
                """,
                (prev_week,),
            )
            db.commit()

            first = game_app._advance_world_research(db, current_week)
            second = game_app._advance_world_research(db, current_week)
            db.commit()

            self.assertFalse(bool(first.get("skipped")))
            self.assertTrue(bool(second.get("skipped")))
            row = db.execute(
                "SELECT progress FROM world_research_progress WHERE element = 'FIRE'"
            ).fetchone()
            self.assertEqual(int(row["progress"]), 50)
            events = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM world_events_log
                WHERE event_type = 'RESEARCH_ADVANCE'
                  AND payload_json LIKE ?
                """,
                (f'%"week_key": "{current_week}"%',),
            ).fetchone()["c"]
            self.assertEqual(int(events), 1)


if __name__ == "__main__":
    unittest.main()

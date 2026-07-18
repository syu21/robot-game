import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FirstUpgradeOnboardingTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, last_seen_at, is_admin, wins, max_unlocked_layer)
                VALUES (?, 'x', ?, ?, 0, 0, 1)
                """,
                ("first_upgrade_user", now, now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("first_upgrade_user",)).fetchone()["id"])
            self.robot_id, self.equipped_ids = self._create_active_robot(db, self.user_id)
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _db(self):
        return game_app.get_db()

    def _user(self):
        return self._db().execute("SELECT * FROM users WHERE id = ?", (self.user_id,)).fetchone()

    def _part(self, db, part_type):
        return db.execute(
            "SELECT * FROM robot_parts WHERE part_type = ? AND is_active = 1 ORDER BY id ASC LIMIT 1",
            (part_type,),
        ).fetchone()

    def _drop(self, db, part_type, *, plus=0):
        part = self._part(db, part_type)
        return int(game_app._create_part_instance_from_master(db, self.user_id, part, plus=plus, status="inventory"))

    def _create_active_robot(self, db, user_id):
        parts = {
            "head": self._drop(db, "HEAD", plus=0),
            "r_arm": self._drop(db, "RIGHT_ARM", plus=0),
            "l_arm": self._drop(db, "LEFT_ARM", plus=0),
            "legs": self._drop(db, "LEGS", plus=0),
        }
        keys = {
            "head": self._part(db, "HEAD")["key"],
            "r_arm": self._part(db, "RIGHT_ARM")["key"],
            "l_arm": self._part(db, "LEFT_ARM")["key"],
            "legs": self._part(db, "LEGS")["key"],
        }
        robot_id = game_app._create_robot_instance(
            db,
            user_id,
            "GuideBot",
            keys["head"],
            keys["r_arm"],
            keys["l_arm"],
            keys["legs"],
            status="active",
        )
        game_app._equip_part_instances_on_robot(db, robot_id, parts)
        db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (robot_id, user_id))
        return int(robot_id), parts

    def _event(self, event_type, payload=None, user_id=None):
        db = self._db()
        db.execute(
            """
            INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
            VALUES (?, ?, ?, ?)
            """,
            (int(time.time()), event_type, json.dumps(payload or {}, ensure_ascii=False), int(user_id or self.user_id)),
        )
        db.commit()

    def _complete_explores(self, count):
        for i in range(count):
            self._event(game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], {"area_key": "layer_1", "result": {"win": True, "i": i}})

    def _start_guide(self):
        db = self._db()
        db.execute(
            """
            UPDATE users
            SET onboarding_first_three_reward_claimed = 1,
                first_upgrade_guide_started_at = ?
            WHERE id = ?
            """,
            (int(time.time()), self.user_id),
        )
        db.commit()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "first_upgrade_user"
        return client

    def test_two_explores_do_not_start_first_upgrade_guide(self):
        with game_app.app.app_context():
            self._complete_explores(2)
            result = game_app._start_onboarding_first_upgrade_guide(self._db(), self._user(), source="battle_result")
            self.assertIsNone(result)

    def test_third_explore_reward_starts_result_guide(self):
        with game_app.app.app_context():
            self._complete_explores(3)
            grant = game_app._grant_onboarding_first_three_reward_if_ready(self._db(), self._user(), area_key="layer_1")
            self.assertTrue(grant["granted"])
            user = self._user()
            guide = game_app._start_onboarding_first_upgrade_guide(self._db(), user, source="battle_result")
            self.assertIsNotNone(guide)
            self.assertIn("新しいパーツ", guide["title"])

    def test_home_next_action_switches_to_first_upgrade_and_keeps_sortie(self):
        with game_app.app.app_context():
            self._complete_explores(3)
            self._start_guide()
            with game_app.app.test_request_context("/"):
                card = game_app._home_next_action_card(
                    self._db(),
                    self._user(),
                    boss_alert_status=[],
                    max_unlocked_layer=1,
                    new_layer_badge=None,
                    unlocked_layer_recent=None,
                    total_explores=3,
                )
        self.assertEqual(card["title"], "持ち帰ったパーツを機体に使おう")
        self.assertEqual(card["cta_label"], "パーツを見比べる")
        self.assertEqual(card["secondary_actions"][0]["label"], "そのまま出撃する")

    def test_parts_guide_shows_single_recommendation_when_better_part_exists(self):
        with game_app.app.app_context():
            db = self._db()
            self._complete_explores(3)
            self._start_guide()
            better_id = self._drop(db, "HEAD", plus=0)
            db.execute(
                """
                UPDATE part_instances
                SET w_hp = 120, w_atk = 120, w_def = 120, w_spd = 120, w_acc = 120, w_cri = 120
                WHERE id = ?
                """,
                (better_id,),
            )
            db.commit()
        response = self._client().get("/parts?onboarding=first_upgrade")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("今の装備と、拾ったパーツを見比べよう", body)
        self.assertEqual(body.count("part-chip is-recommended"), 1)

    def test_parts_guide_does_not_recommend_without_better_part_and_does_not_complete(self):
        with game_app.app.app_context():
            self._complete_explores(3)
            self._start_guide()
        response = self._client().get("/parts?onboarding=first_upgrade")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("part-chip is-recommended", body)
        with game_app.app.app_context():
            user = self._user()
            self.assertEqual(int(user["first_upgrade_guide_completed_at"] or 0), 0)

    def test_changed_parts_complete_guide_once_with_audit_payload(self):
        with game_app.app.app_context():
            db = self._db()
            self._complete_explores(3)
            self._start_guide()
            before = dict(self.equipped_ids)
            after = dict(before)
            after["head"] = self._drop(db, "HEAD", plus=5)
            changed = game_app._first_upgrade_changed_part_types(db, before, after)
            first = game_app._complete_onboarding_first_upgrade(
                db,
                self._user(),
                active_robot_id_before=self.robot_id,
                active_robot_id_after=self.robot_id + 1,
                changed_part_types=changed,
            )
            second = game_app._complete_onboarding_first_upgrade(
                db,
                self._user(),
                active_robot_id_before=self.robot_id,
                active_robot_id_after=self.robot_id + 1,
                changed_part_types=changed,
            )
            rows = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["ONBOARDING_FIRST_UPGRADE_COMPLETE"]),
            ).fetchall()
            self.assertTrue(first)
            self.assertFalse(second)
            self.assertEqual(len(rows), 1)
            payload = json.loads(rows[0]["payload_json"])
            self.assertEqual(payload["source"], "build_confirm")
            self.assertEqual(payload["changed_part_types"], ["HEAD"])

    def test_admin_test_and_analytics_excluded_are_not_targets(self):
        with game_app.app.app_context():
            self._complete_explores(3)
            self._start_guide()
            db = self._db()
            db.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (self.user_id,))
            db.commit()
            self.assertFalse(game_app._onboarding_first_upgrade_should_show(db, self._user()))
            db.execute("UPDATE users SET is_admin = 0, analytics_excluded = 1 WHERE id = ?", (self.user_id,))
            db.commit()
            self.assertFalse(game_app._onboarding_first_upgrade_should_show(db, self._user()))
            db.execute(
                "UPDATE users SET analytics_excluded = 0, username = 'test_first_upgrade' WHERE id = ?",
                (self.user_id,),
            )
            db.commit()
            self.assertFalse(game_app._onboarding_first_upgrade_should_show(db, self._user()))


if __name__ == "__main__":
    unittest.main()

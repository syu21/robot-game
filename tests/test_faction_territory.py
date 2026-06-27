import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactionTerritoryTests(unittest.TestCase):
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
            self.admin_id = self._create_user(db, "territory_admin", now, "aurix", is_admin=1)
            self.aurix_user = self._create_user(db, "territory_aurix", now, "aurix")
            self.ignis_user = self._create_user(db, "territory_ignis", now, "ignis")
            self.ventra_user = self._create_user(db, "territory_ventra", now, "ventra")
            self.week_key = game_app.get_current_week_key()
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _create_user(self, db, username, now, faction, *, is_admin=0):
        db.execute(
            """
            INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer, faction)
            VALUES (?, ?, ?, ?, 0, 1, ?)
            """,
            (username, "x", now, int(is_admin), faction),
        )
        user_id = int(db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"])
        game_app.initialize_new_user(db, user_id)
        return user_id

    def _client(self, user_id=None, username="territory_aurix"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id or self.aurix_user)
            session["username"] = username
        return client

    def _log_event(self, db, user_id, event_type, *, payload=None):
        db.execute(
            """
            INSERT INTO world_events_log (created_at, event_type, payload_json, user_id, request_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                int(time.time()),
                event_type,
                json.dumps(payload or {}, ensure_ascii=False),
                int(user_id),
                f"territory-{user_id}-{event_type}-{time.time_ns()}",
            ),
        )

    def _seed_component_scores(self, db):
        for _ in range(3):
            self._log_event(db, self.aurix_user, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"])
        self._log_event(db, self.ignis_user, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"])
        db.execute(
            """
            INSERT INTO faction_guardian_attacks
            (week_key, attacker_faction_key, target_faction_key, guardian_id, attacker_user_id,
             source_event_type, source_event_id, request_id, damage, created_at)
            VALUES (?, 'aurix', 'ignis', 1, ?, 'test.guardian', 101, 'territory-guardian', 80, ?)
            """,
            (self.week_key, self.aurix_user, game_app.now_str()),
        )
        db.execute(
            """
            INSERT INTO faction_representative_matches
            (week_key, match_key, faction_a_key, faction_b_key, winner_faction_key, result_status, created_at, completed_at, updated_at)
            VALUES (?, 'territory_rep', 'ignis', 'ventra', 'ignis', 'completed', ?, ?, ?)
            """,
            (self.week_key, game_app.now_str(), game_app.now_str(), game_app.now_str()),
        )
        db.execute(
            """
            INSERT INTO faction_guardian_duels
            (week_key, duel_key, faction_a_key, faction_b_key, winner_faction_key, result_status, created_at, completed_at, updated_at)
            VALUES (?, 'territory_duel', 'ventra', 'aurix', 'ventra', 'completed', ?, ?, ?)
            """,
            (self.week_key, game_app.now_str(), game_app.now_str(), game_app.now_str()),
        )
        game_app.grant_faction_facility_material(db, "ventra", self.ventra_user, "test.territory.facility", 201, 90, week_key=self.week_key)

    def test_ensure_territory_areas_is_idempotent(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            cols = {row["name"] for row in db.execute("PRAGMA table_info(faction_territory_states)").fetchall()}
            self.assertIn("control_reason", cols)
            first = game_app.ensure_faction_territory_areas(db)
            second = game_app.ensure_faction_territory_areas(db)
            self.assertEqual(first["created_count"], 5)
            self.assertEqual(second["created_count"], 0)
            self.assertEqual(len(game_app.get_faction_territory_area_rows(db)), 5)

    def test_scores_include_all_components_and_no_data_is_safe(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            empty = game_app.calculate_faction_territory_scores(db, self.week_key)
            self.assertEqual(len(empty["scores"]), 15)
            self._seed_component_scores(db)
            result = game_app.calculate_faction_territory_scores(db, self.week_key)
            rows = {(row["area_key"], row["faction_key"]): row for row in result["scores"]}
            self.assertGreater(rows[("central_observation", "aurix")]["activity_score"], 0)
            self.assertEqual(rows[("north_bastion", "aurix")]["guardian_score"], 80)
            self.assertEqual(rows[("east_core", "ignis")]["representative_score"], 100)
            self.assertEqual(rows[("west_wind", "ventra")]["guardian_duel_score"], 100)
            self.assertEqual(rows[("outer_trial", "ventra")]["facility_score"], 90)

    def test_update_states_tie_rule_finalize_and_world_log_are_stable(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            first = game_app.update_faction_territory_states(db, self.week_key, finalize=False)
            self.assertEqual(first["updated_count"], 5)
            state = db.execute(
                "SELECT controlling_faction_key FROM faction_territory_states WHERE week_key = ? AND area_key = 'east_core'",
                (self.week_key,),
            ).fetchone()
            self.assertEqual(state["controlling_faction_key"], "ignis")
            final = game_app.update_faction_territory_states(db, self.week_key, finalize=True)
            again = game_app.update_faction_territory_states(db, self.week_key, finalize=True)
            self.assertTrue(final["emitted_world_event"])
            self.assertFalse(again["emitted_world_event"])
            count = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ?",
                (game_app.FACTION_TERRITORY_RESULT_EVENT_TYPE,),
            ).fetchone()["c"]
            self.assertEqual(count, 1)
            finalized = db.execute("SELECT COUNT(*) AS c FROM faction_territory_states WHERE is_finalized = 1").fetchone()["c"]
            self.assertEqual(finalized, 5)

    def test_pages_and_admin_routes_show_territory(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._seed_component_scores(db)
            game_app.update_faction_territory_states(db, self.week_key, finalize=False)
            db.commit()
        client = self._client()
        self.assertIn("陣営領土マップ", client.get("/world").get_data(as_text=True))
        self.assertIn("自陣営の研究影響エリア", client.get("/faction").get_data(as_text=True))
        self.assertIn("今週の研究影響エリア", client.get("/comms/faction").get_data(as_text=True))
        self.assertEqual(client.get("/admin/factions/territory").status_code, 403)
        admin = self._client(self.admin_id, "territory_admin")
        self.assertEqual(admin.get("/admin/factions/territory").status_code, 200)
        self.assertEqual(admin.post("/admin/factions/territory/ensure", data={"week_key": self.week_key}).status_code, 302)
        self.assertEqual(admin.post("/admin/factions/territory/recalculate", data={"week_key": self.week_key}).status_code, 302)
        self.assertEqual(admin.post("/admin/factions/territory/finalize", data={"week_key": self.week_key}).status_code, 302)

    def test_territory_does_not_change_robot_stats(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            before = db.execute("SELECT * FROM robot_instances WHERE user_id = ? ORDER BY id LIMIT 1", (self.aurix_user,)).fetchone()
            self._seed_component_scores(db)
            game_app.update_faction_territory_states(db, self.week_key, finalize=True)
            after = db.execute("SELECT * FROM robot_instances WHERE user_id = ? ORDER BY id LIMIT 1", (self.aurix_user,)).fetchone()
            self.assertEqual(dict(before), dict(after))


if __name__ == "__main__":
    unittest.main()

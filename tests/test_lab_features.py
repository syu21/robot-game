import io
import os
import tempfile
import time
import unittest

from PIL import Image

import app as game_app
import init_db
from services.lab import LAB_RACE_ENTRY_TARGET, fill_npc_entries, simulate_race


def _png_bytes(*, size=(128, 128), transparent=True):
    mode = "RGBA" if transparent else "RGB"
    bg = (0, 0, 0, 0) if transparent else (20, 40, 60)
    img = Image.new(mode, size, bg)
    if transparent:
        inner = Image.new("RGBA", (size[0] // 2, size[1] // 2), (220, 120, 80, 255))
        img.alpha_composite(inner, (size[0] // 4, size[1] // 4))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class LabSimulationTests(unittest.TestCase):
    def test_simulation_is_deterministic_with_same_seed(self):
        base_entries = [
            {
                "entry_order": 1,
                "source_type": "robot_instance",
                "display_name": "Speedy",
                "user_id": 1,
                "robot_instance_id": 10,
                "submission_id": None,
                "icon_path": None,
                "hp": 16,
                "atk": 8,
                "def": 7,
                "spd": 18,
                "acc": 12,
                "cri": 10,
            },
            {
                "entry_order": 2,
                "source_type": "robot_instance",
                "display_name": "Tanky",
                "user_id": 2,
                "robot_instance_id": 11,
                "submission_id": None,
                "icon_path": None,
                "hp": 24,
                "atk": 8,
                "def": 16,
                "spd": 8,
                "acc": 10,
                "cri": 5,
            },
        ]
        entries = fill_npc_entries(base_entries, 424242, target=LAB_RACE_ENTRY_TARGET)
        first = simulate_race(entries, 424242, "scrapyard_dash")
        second = simulate_race(entries, 424242, "scrapyard_dash")
        self.assertEqual(first["results"], second["results"])
        self.assertEqual(first["frames"], second["frames"])

    def test_fill_npc_entries_and_unique_finish_order(self):
        entries = fill_npc_entries(
            [
                {
                    "entry_order": 1,
                    "source_type": "robot_instance",
                    "display_name": "Solo",
                    "user_id": 1,
                    "robot_instance_id": 10,
                    "submission_id": None,
                    "icon_path": None,
                    "hp": 20,
                    "atk": 9,
                    "def": 9,
                    "spd": 12,
                    "acc": 11,
                    "cri": 8,
                }
            ],
            12345,
            target=LAB_RACE_ENTRY_TARGET,
        )
        self.assertEqual(len(entries), LAB_RACE_ENTRY_TARGET)
        npc_entries = [item for item in entries if item.get("source_type") == "npc"]
        self.assertTrue(npc_entries)
        self.assertTrue(all(str(item.get("icon_path") or "").startswith("enemies/") for item in npc_entries))
        race = simulate_race(entries, 12345, "gravity_lane")
        ranks = [row["final_rank"] for row in race["results"]]
        self.assertEqual(sorted(ranks), list(range(1, LAB_RACE_ENTRY_TARGET + 1)))

    def test_simulation_frames_include_lane_and_segment_metadata(self):
        entries = fill_npc_entries(
            [
                {
                    "entry_order": 1,
                    "source_type": "robot_instance",
                    "display_name": "Scout",
                    "user_id": 1,
                    "robot_instance_id": 12,
                    "submission_id": None,
                    "icon_path": None,
                    "hp": 18,
                    "atk": 9,
                    "def": 8,
                    "spd": 15,
                    "acc": 12,
                    "cri": 9,
                }
            ],
            11111,
            target=LAB_RACE_ENTRY_TARGET,
        )
        race = simulate_race(entries, 11111, "scrapyard_sprint")
        self.assertTrue(race["frames"])
        first_entry = race["frames"][0]["entries"][0]
        self.assertIn("lane_index", first_entry)
        self.assertIn("segment_index", first_entry)
        self.assertIn("is_finished", first_entry)

    def test_speedy_entry_is_faster_but_more_accident_prone_over_many_seeds(self):
        speed_times = []
        speed_accidents = []
        tank_times = []
        tank_accidents = []
        for seed in range(100, 112):
            base_entries = [
                {
                    "entry_order": 1,
                    "source_type": "robot_instance",
                    "display_name": "Speedy",
                    "user_id": 1,
                    "robot_instance_id": 10,
                    "submission_id": None,
                    "icon_path": None,
                    "hp": 15,
                    "atk": 8,
                    "def": 6,
                    "spd": 20,
                    "acc": 10,
                    "cri": 10,
                },
                {
                    "entry_order": 2,
                    "source_type": "robot_instance",
                    "display_name": "Tanky",
                    "user_id": 2,
                    "robot_instance_id": 11,
                    "submission_id": None,
                    "icon_path": None,
                    "hp": 26,
                    "atk": 7,
                    "def": 18,
                    "spd": 7,
                    "acc": 11,
                    "cri": 5,
                },
            ]
            entries = fill_npc_entries(base_entries, seed, target=LAB_RACE_ENTRY_TARGET)
            race = simulate_race(entries, seed, "scrapyard_dash")
            speedy = next(row for row in race["results"] if row["display_name"] == "Speedy")
            tanky = next(row for row in race["results"] if row["display_name"] == "Tanky")
            speed_times.append(speedy["finish_time_ms"])
            speed_accidents.append(speedy["accident_count"])
            tank_times.append(tanky["finish_time_ms"])
            tank_accidents.append(tanky["accident_count"])
        self.assertLess(sum(speed_times) / len(speed_times), sum(tank_times) / len(tank_times))
        self.assertGreater(sum(speed_accidents) / len(speed_accidents), sum(tank_accidents) / len(tank_accidents))


class LabRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True
        self.created_files = []

        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 0, 0, 0, 1)
                """,
                ("lab_user", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("lab_user",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.user_id)
            self.robot_id = int(
                db.execute("SELECT active_robot_id FROM users WHERE id = ?", (self.user_id,)).fetchone()["active_robot_id"]
            )
            db.execute("UPDATE robot_instances SET name = ? WHERE id = ?", ("WatcherBot", self.robot_id))
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 1, 1, 0, 1)
                """,
                ("lab_admin", "x", now),
            )
            self.admin_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("lab_admin",)).fetchone()["id"])
            db.commit()

    def tearDown(self):
        for path in self.created_files:
            try:
                abs_path = os.path.join(game_app.STATIC_ROOT, path)
                if os.path.exists(abs_path):
                    os.remove(abs_path)
            except Exception:
                pass
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self, *, admin=False):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            if admin:
                session["user_id"] = self.admin_id
                session["username"] = "lab_admin"
            else:
                session["user_id"] = self.user_id
                session["username"] = "lab_user"
        return client

    def test_lab_race_entry_creates_finished_race_and_audit_logs(self):
        client = self._client()
        resp = client.post(
            "/lab/race/entry",
            data={"robot_instance_id": self.robot_id, "course_key": "scrapyard_dash"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/lab/race/legacy/watch/", resp.headers["Location"])

        with game_app.app.app_context():
            db = game_app.get_db()
            race = db.execute("SELECT * FROM lab_races ORDER BY id DESC LIMIT 1").fetchone()
            self.assertIsNotNone(race)
            self.assertEqual(race["status"], "finished")
            entry_count = int(
                db.execute("SELECT COUNT(*) AS c FROM lab_race_entries WHERE race_id = ?", (race["id"],)).fetchone()["c"] or 0
            )
            frame_count = int(
                db.execute("SELECT COUNT(*) AS c FROM lab_race_frames WHERE race_id = ?", (race["id"],)).fetchone()["c"] or 0
            )
            record_count = int(
                db.execute("SELECT COUNT(*) AS c FROM lab_race_records WHERE race_id = ?", (race["id"],)).fetchone()["c"] or 0
            )
            npc_icon_count = int(
                db.execute(
                    """
                    SELECT COUNT(*) AS c
                    FROM lab_race_entries
                    WHERE race_id = ? AND source_type = 'npc' AND icon_path LIKE 'enemies/%'
                    """,
                    (race["id"],),
                ).fetchone()["c"]
                or 0
            )
            self.assertEqual(entry_count, LAB_RACE_ENTRY_TARGET)
            self.assertGreater(frame_count, 0)
            self.assertEqual(record_count, LAB_RACE_ENTRY_TARGET)
            self.assertGreater(npc_icon_count, 0)
            event_types = {
                row["event_type"]
                for row in db.execute(
                    "SELECT event_type FROM world_events_log WHERE event_type LIKE 'audit.lab.%' OR event_type LIKE 'LAB_%'"
                ).fetchall()
            }
            self.assertIn(game_app.AUDIT_EVENT_TYPES["LAB_RACE_ENTRY"], event_types)
            self.assertIn(game_app.AUDIT_EVENT_TYPES["LAB_RACE_START"], event_types)
            self.assertIn(game_app.AUDIT_EVENT_TYPES["LAB_RACE_FINISH"], event_types)
            self.assertIn("LAB_RACE_WIN", event_types)

    def test_lab_watch_page_embeds_raw_json_frames(self):
        client = self._client()
        resp = client.post(
            "/lab/race/entry",
            data={"robot_instance_id": self.robot_id, "course_key": "scrapyard_dash"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        watch = client.get(resp.headers["Location"])
        self.assertEqual(watch.status_code, 200)
        html = watch.get_data(as_text=True)
        self.assertIn('"frame_no"', html)
        self.assertNotIn("&#34;frame_no&#34;", html)
        self.assertIn('"display_name": "WatcherBot"', html)
        self.assertIn('"is_user_entry": true', html)
        self.assertIn('data-lab-race-track="1"', html)
        self.assertIn('data-lab-race-roster="1"', html)
        self.assertIn('data-lab-race-frame-label="1"', html)
        self.assertIn('"track_icon_url":', html)
        self.assertIn('data-lab-race-segment-index="0"', html)
        self.assertIn("L01", html)

    def test_lab_upload_requires_transparent_png_and_approval_controls_visibility(self):
        client = self._client()

        bad_resp = client.post(
            "/lab/upload",
            data={
                "title": "Bad",
                "comment": "opaque",
                "image": (io.BytesIO(_png_bytes(transparent=False)), "bad.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(bad_resp.status_code, 200)
        self.assertIn("透過付きPNGのみ投稿できます", bad_resp.get_data(as_text=True))

        good_resp = client.post(
            "/lab/upload",
            data={
                "title": "GlassBot",
                "comment": "transparent bot",
                "image": (io.BytesIO(_png_bytes()), "glassbot.png"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(good_resp.status_code, 200)
        self.assertIn("投稿を受け付けました", good_resp.get_data(as_text=True))

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT * FROM lab_robot_submissions WHERE title = ?", ("GlassBot",)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["status"], "pending")
            self.created_files.extend([row["image_path"], row["thumb_path"]])

        showcase_before = client.get("/lab/showcase")
        self.assertNotIn("GlassBot", showcase_before.get_data(as_text=True))

        admin_client = self._client(admin=True)
        approve_resp = admin_client.post(
            f"/admin/lab/submissions/{row['id']}/approve",
            data={"moderation_note": "[pick]", "status": "pending"},
            follow_redirects=True,
        )
        self.assertEqual(approve_resp.status_code, 200)

        showcase_after = client.get("/lab/showcase")
        self.assertIn("GlassBot", showcase_after.get_data(as_text=True))

        disable_resp = admin_client.post(
            f"/admin/lab/submissions/{row['id']}/disable",
            data={"moderation_note": "hide", "status": "approved"},
            follow_redirects=True,
        )
        self.assertEqual(disable_resp.status_code, 200)
        showcase_disabled = client.get("/lab/showcase")
        self.assertNotIn("GlassBot", showcase_disabled.get_data(as_text=True))

    def test_lab_like_is_not_duplicated_and_report_is_saved(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            cur = db.execute(
                """
                INSERT INTO lab_robot_submissions
                (user_id, title, comment, image_path, thumb_path, status, created_at, updated_at, approved_at, approved_by_user_id)
                VALUES (?, ?, ?, ?, ?, 'approved', ?, ?, ?, ?)
                """,
                (
                    self.user_id,
                    "LikeBot",
                    "ready",
                    game_app.DEFAULT_BADGE_REL,
                    game_app.DEFAULT_BADGE_REL,
                    now,
                    now,
                    now,
                    self.admin_id,
                ),
            )
            self.submission_id = int(cur.lastrowid)
            db.commit()

        client = self._client()
        first = client.post(f"/lab/showcase/{self.submission_id}/like", follow_redirects=True)
        second = client.post(f"/lab/showcase/{self.submission_id}/like", follow_redirects=True)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertIn("既にいいねしています", second.get_data(as_text=True))
        report = client.post(
            f"/lab/showcase/{self.submission_id}/report",
            data={"reason": "spam"},
            follow_redirects=True,
        )
        self.assertEqual(report.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            likes = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM lab_submission_likes WHERE submission_id = ?",
                    (self.submission_id,),
                ).fetchone()["c"]
                or 0
            )
            reports = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM lab_submission_reports WHERE submission_id = ?",
                    (self.submission_id,),
                ).fetchone()["c"]
                or 0
            )
            self.assertEqual(likes, 1)
            self.assertEqual(reports, 1)


if __name__ == "__main__":
    unittest.main()

import io
import json
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

    def test_lab_ai_generate_links_and_audit_sources(self):
        client = self._client()
        lab_resp = client.get("/lab")
        self.assertEqual(lab_resp.status_code, 200)
        lab_html = lab_resp.get_data(as_text=True)
        self.assertIn("タイピング射撃試験", lab_html)
        self.assertIn("/lab/typing", lab_html)
        self.assertIn("AIロボ生成", lab_html)
        self.assertIn("研究所AIでロボを作る", lab_html)
        self.assertIn("/lab/ai-robot-generate?source=lab_top", lab_html)
        self.assertIn('target="_blank"', lab_html)
        self.assertIn('rel="noopener noreferrer"', lab_html)

        upload_resp = client.get("/lab/upload")
        self.assertEqual(upload_resp.status_code, 200)
        upload_html = upload_resp.get_data(as_text=True)
        self.assertIn("ロボ画像をまだ持っていない方へ", upload_html)
        self.assertIn("研究所AIでロボを作れます", upload_html)
        self.assertIn("作ったPNG画像を、そのままここにアップできます", upload_html)
        self.assertIn("透過PNG・正方形画像をそのまま使えます", upload_html)
        self.assertIn("/lab/ai-robot-generate?source=lab_upload", upload_html)

        for source in ("lab_top", "lab_upload"):
            resp = client.get(f"/lab/ai-robot-generate?source={source}", follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.headers["Location"], game_app.LAB_AI_ROBOT_GENERATOR_URL)

        with game_app.app.app_context():
            db = game_app.get_db()
            rows = db.execute(
                """
                SELECT payload_json
                FROM world_events_log
                WHERE event_type = ?
                ORDER BY id ASC
                """,
                (game_app.AUDIT_EVENT_TYPES["LAB_AI_GENERATE_CLICK"],),
            ).fetchall()
            self.assertEqual(len(rows), 2)
            payloads = [json.loads(row["payload_json"]) for row in rows]
            self.assertEqual([item["source"] for item in payloads], ["lab_top", "lab_upload"])
            self.assertTrue(all(item["target"] == game_app.LAB_AI_ROBOT_GENERATOR_TARGET for item in payloads))
            self.assertTrue(all(item["url"] == game_app.LAB_AI_ROBOT_GENERATOR_URL for item in payloads))

    def test_lab_mini_initial_grant_rename_care_and_catalog(self):
        client = self._client(admin=True)
        resp = client.get("/lab/mini")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("ミニロボ培養室", html)
        self.assertIn("ケルベロス", html)
        self.assertIn("フェニックス", html)
        self.assertIn("ヒュドラ", html)

        selected = client.post("/lab/mini/select", data={"species_key": "hydra"}, follow_redirects=True)
        self.assertEqual(selected.status_code, 200)
        self.assertIn("ヒュドラ", selected.get_data(as_text=True))

        with game_app.app.app_context():
            db = game_app.get_db()
            robot = db.execute(
                "SELECT * FROM user_mini_robots WHERE user_id = ? AND species_key = 'hydra'",
                (self.admin_id,),
            ).fetchone()
            self.assertIsNotNone(robot)
            create_log = db.execute(
                "SELECT COUNT(*) AS c FROM mini_robot_logs WHERE mini_robot_id = ? AND event_type = 'create'",
                (int(robot["id"]),),
            ).fetchone()["c"]
            self.assertEqual(int(create_log), 1)

        rename = client.post("/lab/mini/rename", data={"nickname": "ポチケル"}, follow_redirects=True)
        self.assertEqual(rename.status_code, 200)
        self.assertIn("ポチケル", rename.get_data(as_text=True))

        care = client.post("/lab/mini/care", data={"action_key": "pet"}, follow_redirects=True)
        self.assertEqual(care.status_code, 200)
        care_html = care.get_data(as_text=True)
        self.assertIn("ごきげん", care_html)
        self.assertIn("ヒュドラ", care_html)

        second = client.post("/lab/mini/care", data={"action_key": "energy"}, follow_redirects=True)
        self.assertEqual(second.status_code, 200)
        self.assertIn("今日はもうお世話済みです", second.get_data(as_text=True))

        catalog = client.get("/lab/mini/catalog")
        self.assertEqual(catalog.status_code, 200)
        catalog_html = catalog.get_data(as_text=True)
        self.assertIn("ミニロボ図鑑", catalog_html)
        self.assertIn("ケルベロス", catalog_html)
        self.assertIn("フェニックス", catalog_html)
        self.assertIn("ヒュドラ", catalog_html)
        self.assertIn("未所持", catalog_html)

    def test_lab_mini_release_flag_controls_public_access(self):
        client = self._client()
        lab_resp = client.get("/lab")
        self.assertEqual(lab_resp.status_code, 200)
        self.assertNotIn("ミニロボ培養室", lab_resp.get_data(as_text=True))

        resp = client.get("/lab/mini", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("準備中", html)
        self.assertNotIn("ケルベロス幼体", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            count = db.execute(
                "SELECT COUNT(*) AS c FROM user_mini_robots WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()["c"]
            self.assertEqual(int(count), 0)

        admin_client = self._client(admin=True)
        release_resp = admin_client.post(
            "/admin/release",
            data={"feature_key": "lab_mini", "state": "public"},
            follow_redirects=True,
        )
        self.assertEqual(release_resp.status_code, 200)
        self.assertIn("ミニロボ培養室", release_resp.get_data(as_text=True))
        self.assertIn("一般公開中", release_resp.get_data(as_text=True))

        public_lab = client.get("/lab")
        self.assertEqual(public_lab.status_code, 200)
        self.assertIn("ミニロボ培養室", public_lab.get_data(as_text=True))

        public_mini = client.get("/lab/mini")
        self.assertEqual(public_mini.status_code, 200)
        self.assertIn("ケルベロス", public_mini.get_data(as_text=True))
        self.assertIn("フェニックス", public_mini.get_data(as_text=True))
        self.assertIn("ヒュドラ", public_mini.get_data(as_text=True))

    def test_lab_typing_pages_and_result_save(self):
        client = self._client()
        play_resp = client.get("/lab/typing")
        self.assertEqual(play_resp.status_code, 200)
        play_html = play_resp.get_data(as_text=True)
        self.assertIn("タイピング射撃試験", play_html)
        self.assertIn("lab_typing.js", play_html)
        self.assertIn("スクラップドローン", play_html)

        payload = {
            "score": 128400,
            "max_combo": 42,
            "typed_count": 58,
            "miss_count": 2,
            "defeated_count": 4,
            "boss_reached": True,
            "boss_defeated": False,
            "remaining_boss_hp": 320,
            "duration_ms": 30000,
            "client_payload": {"version": 1},
        }
        result_resp = client.post("/lab/typing/result", json=payload)
        self.assertEqual(result_resp.status_code, 200)
        result_json = result_resp.get_json()
        self.assertTrue(result_json["ok"])
        self.assertGreater(int(result_json["run_id"]), 0)

        history_resp = client.get("/lab/typing/history")
        self.assertEqual(history_resp.status_code, 200)
        history_html = history_resp.get_data(as_text=True)
        self.assertIn("週間ランキング TOP10", history_html)
        self.assertIn("128,400", history_html)

        with game_app.app.app_context():
            db = game_app.get_db()
            run = db.execute("SELECT * FROM lab_typing_runs WHERE id = ?", (result_json["run_id"],)).fetchone()
            self.assertIsNotNone(run)
            self.assertEqual(int(run["score"]), 128400)
            event_types = {
                row["event_type"]
                for row in db.execute(
                    "SELECT event_type FROM world_events_log WHERE event_type IN (?, ?)",
                    (
                        game_app.AUDIT_EVENT_TYPES["LAB_TYPING_START"],
                        game_app.AUDIT_EVENT_TYPES["LAB_TYPING_FINISH"],
                    ),
                ).fetchall()
            }
            self.assertIn(game_app.AUDIT_EVENT_TYPES["LAB_TYPING_START"], event_types)
            self.assertIn(game_app.AUDIT_EVENT_TYPES["LAB_TYPING_FINISH"], event_types)

    def test_lab_typing_result_rejects_invalid_values(self):
        client = self._client()
        invalid_resp = client.post(
            "/lab/typing/result",
            json={
                "score": 5_000_001,
                "max_combo": 1,
                "typed_count": 1,
                "miss_count": 0,
                "defeated_count": 0,
                "duration_ms": 30000,
            },
        )
        self.assertEqual(invalid_resp.status_code, 400)
        self.assertFalse(invalid_resp.get_json()["ok"])

        invalid_duration = client.post(
            "/lab/typing/result",
            json={
                "score": 10,
                "max_combo": 1,
                "typed_count": 1,
                "miss_count": 0,
                "defeated_count": 0,
                "duration_ms": 12000,
            },
        )
        self.assertEqual(invalid_duration.status_code, 400)

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
                "ai_generation_declared": "no_ai",
                "terms_accept": "1",
                "image": (io.BytesIO(_png_bytes(transparent=False)), "bad.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(bad_resp.status_code, 200)
        self.assertIn("透過付きPNGのみ投稿できます", bad_resp.get_data(as_text=True))

        no_terms_resp = client.post(
            "/lab/upload",
            data={
                "title": "NoTerms",
                "comment": "transparent bot",
                "ai_generation_declared": "no_ai",
                "image": (io.BytesIO(_png_bytes()), "noterms.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(no_terms_resp.status_code, 200)
        no_terms_html = no_terms_resp.get_data(as_text=True)
        self.assertIn("利用条件への同意が必要です", no_terms_html)
        self.assertIn('data-lab-radar-polygon', no_terms_html)
        self.assertIn("現在合計: 30 / 36", no_terms_html)
        self.assertIn("lab_upload.js", no_terms_html)

        over_stat_resp = client.post(
            "/lab/upload",
            data={
                "title": "TooStrong",
                "comment": "too much",
                "ai_generation_declared": "no_ai",
                "terms_accept": "1",
                "chart_hp_score": "10",
                "chart_atk_score": "10",
                "chart_def_score": "10",
                "chart_spd_score": "10",
                "chart_acc_score": "10",
                "chart_cri_score": "10",
                "image": (io.BytesIO(_png_bytes()), "toostrong.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(over_stat_resp.status_code, 200)
        self.assertIn("参考スペックの合計は36までです", over_stat_resp.get_data(as_text=True))

        good_resp = client.post(
            "/lab/upload",
            data={
                "title": "GlassBot",
                "comment": "transparent bot",
                "credit_name": "Glass Lab",
                "ai_generation_declared": "no_ai",
                "source_note": "自作PNG",
                "tags": "prototype",
                "intended_style_key": "prototype",
                "terms_accept": "1",
                "image": (io.BytesIO(_png_bytes()), "glassbot.png"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(good_resp.status_code, 200)
        self.assertIn("投稿を受け付けました", good_resp.get_data(as_text=True))
        self.assertIn("確認まで少しお時間をいただく場合があります", good_resp.get_data(as_text=True))

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT * FROM lab_robot_submissions WHERE title = ?", ("GlassBot",)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["status"], "pending")
            self.assertEqual(row["terms_version"], game_app.LAB_TERMS_VERSION)
            self.assertEqual(row["ai_generation_declared"], "no_ai")
            self.assertIn("prototype", row["tags_json"])
            self.assertEqual(int(row["chart_hp"]), 50)
            self.created_files.extend([row["image_path"], row["thumb_path"]])

        showcase_before = client.get("/lab/showcase")
        self.assertNotIn("GlassBot", showcase_before.get_data(as_text=True))

        admin_client = self._client(admin=True)
        admin_pending = admin_client.get("/admin/lab/submissions")
        self.assertEqual(admin_pending.status_code, 200)
        self.assertIn("GlassBot", admin_pending.get_data(as_text=True))
        approve_resp = admin_client.post(
            f"/admin/lab/submissions/{row['id']}/approve",
            data={
                "moderation_note": "[pick]",
                "status": "pending",
                "tags": "prototype",
                "intended_style_key": "prototype",
                "chart_hp": "80",
                "chart_atk": "60",
                "chart_def": "55",
                "chart_spd": "40",
                "chart_acc": "70",
                "chart_cri": "45",
                "is_featured": "1",
                "is_adoption_candidate": "1",
                "adoption_stage": "candidate",
                "adoption_type": "enemy",
                "credit_name": "Glass Lab",
            },
            follow_redirects=True,
        )
        self.assertEqual(approve_resp.status_code, 200)
        admin_approved = admin_client.get("/admin/lab/submissions?status=approved")
        self.assertEqual(admin_approved.status_code, 200)
        self.assertIn("採用情報更新", admin_approved.get_data(as_text=True))

        showcase_after = client.get("/lab/showcase")
        showcase_html = showcase_after.get_data(as_text=True)
        self.assertIn("GlassBot", showcase_html)
        self.assertIn("採用候補", showcase_html)
        self.assertIn("試作", showcase_html)
        self.assertIn("投稿者: Glass Lab", showcase_html)
        self.assertNotIn("投稿者: lab_user", showcase_html)
        self.assertIn("lab-radar-panel is-showcase", showcase_html)
        self.assertIn("lab-radar-fill", showcase_html)
        detail_resp = client.get(f"/lab/showcase/{row['id']}")
        detail_html = detail_resp.get_data(as_text=True)
        self.assertEqual(detail_resp.status_code, 200)
        self.assertIn("投稿者: Glass Lab", detail_html)
        self.assertNotIn("投稿者: lab_user", detail_html)
        self.assertIn("lab-detail-grid is-pair", detail_html)
        self.assertIn("lab-detail-summary-card", detail_html)
        self.assertIn("lab-detail-spec-card", detail_html)
        self.assertIn("lab-radar-panel is-detail", detail_html)
        self.assertIn("研究参考スペックのレーダーチャート", detail_html)
        self.assertNotIn("管理者向け投稿情報", detail_html)
        admin_detail_resp = admin_client.get(f"/lab/showcase/{row['id']}")
        admin_detail_html = admin_detail_resp.get_data(as_text=True)
        self.assertEqual(admin_detail_resp.status_code, 200)
        self.assertIn("lab-detail-action-card", admin_detail_html)
        self.assertIn("lab-detail-admin-card", admin_detail_html)
        self.assertIn("管理者向け投稿情報", admin_detail_html)
        candidate_resp = client.get("/lab/showcase?sort=candidate")
        self.assertIn("GlassBot", candidate_resp.get_data(as_text=True))
        my_resp = client.get("/lab/my-submissions")
        self.assertIn("GlassBot", my_resp.get_data(as_text=True))

        with game_app.app.app_context():
            db = game_app.get_db()
            approved_row = db.execute("SELECT * FROM lab_robot_submissions WHERE id = ?", (row["id"],)).fetchone()
            self.assertEqual(int(approved_row["is_featured"]), 1)
            self.assertEqual(int(approved_row["is_adoption_candidate"]), 1)
            self.assertEqual(approved_row["adoption_stage"], "candidate")
            self.assertEqual(approved_row["adoption_type"], "enemy")
            self.assertEqual(int(approved_row["chart_hp"]), 80)
            adoption = db.execute(
                "SELECT * FROM lab_submission_adoptions WHERE submission_id = ?",
                (row["id"],),
            ).fetchone()
            self.assertIsNotNone(adoption)
            self.assertEqual(adoption["status"], "candidate")
            self.assertEqual(adoption["adoption_type"], "enemy")
            audit_types = {
                item["event_type"]
                for item in db.execute(
                    "SELECT event_type FROM world_events_log WHERE entity_type = 'lab_submission' AND entity_id = ?",
                    (row["id"],),
                ).fetchall()
            }
            self.assertIn(game_app.AUDIT_EVENT_TYPES["LAB_SUBMISSION_CREATE"], audit_types)
            self.assertIn(game_app.AUDIT_EVENT_TYPES["LAB_SUBMISSION_APPROVE"], audit_types)

            now = int(time.time())
            reject_cur = db.execute(
                """
                INSERT INTO lab_robot_submissions
                (user_id, title, comment, image_path, thumb_path, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    self.user_id,
                    "RejectBot",
                    "pending",
                    game_app.DEFAULT_BADGE_REL,
                    game_app.DEFAULT_BADGE_REL,
                    now,
                    now,
                ),
            )
            reject_id = int(reject_cur.lastrowid)
            db.commit()

        reject_resp = admin_client.post(
            f"/admin/lab/submissions/{reject_id}/reject",
            data={"moderation_note": "revise", "reject_reason_key": "guideline", "status": "pending"},
            follow_redirects=True,
        )
        self.assertEqual(reject_resp.status_code, 200)
        with game_app.app.app_context():
            db = game_app.get_db()
            rejected = db.execute("SELECT status FROM lab_robot_submissions WHERE id = ?", (reject_id,)).fetchone()
            self.assertEqual(rejected["status"], "rejected")
            reject_audit = db.execute(
                "SELECT id FROM world_events_log WHERE event_type = ? AND entity_type = 'lab_submission' AND entity_id = ?",
                (game_app.AUDIT_EVENT_TYPES["LAB_SUBMISSION_REJECT"], reject_id),
            ).fetchone()
            self.assertIsNotNone(reject_audit)

        disable_resp = admin_client.post(
            f"/admin/lab/submissions/{row['id']}/disable",
            data={"moderation_note": "hide", "status": "approved"},
            follow_redirects=True,
        )
        self.assertEqual(disable_resp.status_code, 200)
        showcase_disabled = client.get("/lab/showcase")
        self.assertNotIn("GlassBot", showcase_disabled.get_data(as_text=True))
        with game_app.app.app_context():
            db = game_app.get_db()
            disable_audit = db.execute(
                "SELECT id FROM world_events_log WHERE event_type = ? AND entity_type = 'lab_submission' AND entity_id = ?",
                (game_app.AUDIT_EVENT_TYPES["LAB_SUBMISSION_DISABLE"], int(row["id"])),
            ).fetchone()
            self.assertIsNotNone(disable_audit)

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

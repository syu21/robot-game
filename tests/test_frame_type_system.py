import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FrameTypeSystemTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 1, 0, 99999, 5)
                """,
                ("frame_tester", "x", now),
            )
            self.user_id = int(
                db.execute("SELECT id FROM users WHERE username = ?", ("frame_tester",)).fetchone()["id"]
            )
            game_app.initialize_new_user(db, self.user_id)
            self.robot_id = int(
                db.execute("SELECT active_robot_id FROM users WHERE id = ?", (self.user_id,)).fetchone()["active_robot_id"]
            )
            self.normal_parts = {
                part_type: db.execute(
                    """
                    SELECT *
                    FROM robot_parts
                    WHERE part_type = ? AND COALESCE(frame_type, 'normal') = 'normal' AND is_active = 1
                    ORDER BY id ASC
                    LIMIT 1
                    """,
                    (part_type,),
                ).fetchone()
                for part_type in ("HEAD", "RIGHT_ARM", "LEFT_ARM", "LEGS")
            }
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "frame_tester"
        return client

    def _create_instance(self, part_key, *, plus=0, status="inventory"):
        with game_app.app.app_context():
            db = game_app.get_db()
            part = game_app._get_part_by_key(db, part_key)
            self.assertIsNotNone(part)
            part_instance_id = int(
                game_app._create_part_instance_from_master(
                    db,
                    self.user_id,
                    part,
                    plus=plus,
                    status=status,
                )
            )
            db.commit()
            return part_instance_id

    def _insert_custom_part(self, *, key, part_type, rarity, frame_type, series, display_name):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            base = self.normal_parts[part_type]
            series_key = series if frame_type == "insect" else None
            series_label = None
            if series_key:
                meta = db.execute(
                    "SELECT display_name FROM series_master WHERE series_key = ?",
                    (series_key,),
                ).fetchone()
                series_label = meta["display_name"] if meta else None
            db.execute(
                """
                INSERT INTO robot_parts (
                    part_type, key, image_path, rarity, element, series,
                    frame_type, series_key, series_label, display_name_ja,
                    offset_x, offset_y, is_active, is_unlocked, created_at
                )
                VALUES (?, ?, ?, ?, 'NORMAL', ?, ?, ?, ?, ?, 0, 0, 1, 1, ?)
                """,
                (
                    part_type,
                    key,
                    base["image_path"],
                    rarity,
                    series,
                    frame_type,
                    series_key,
                    series_label,
                    display_name,
                    now,
                ),
            )
            row = db.execute("SELECT * FROM robot_parts WHERE key = ?", (key,)).fetchone()
            db.commit()
            return row

    def _grant_evolution_core(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET max_unlocked_layer = 5 WHERE id = ?", (self.user_id,))
            game_app._grant_player_core(db, self.user_id, game_app.EVOLUTION_CORE_KEY, qty=1)
            db.commit()

    def test_existing_robot_defaults_to_normal_frame(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            robot = db.execute("SELECT frame_type FROM robot_instances WHERE id = ?", (self.robot_id,)).fetchone()
            self.assertEqual(robot["frame_type"], "normal")
        html = self._client().get(f"/robots/{self.robot_id}").get_data(as_text=True)
        self.assertIn("フレーム: 通常型", html)

    def test_build_filters_candidates_by_frame_type(self):
        normal_head_id = self._create_instance(self.normal_parts["HEAD"]["key"])
        insect_head_id = self._create_instance("head_kabuto")
        dinosaur_head_id = self._create_instance("head_n_dino_tyranno")
        client = self._client()

        normal_html = client.get("/build?frame_type=normal").get_data(as_text=True)
        self.assertIn(f'id="head_key_{normal_head_id}"', normal_html)
        self.assertNotIn(f'id="head_key_{insect_head_id}"', normal_html)
        self.assertNotIn(f'id="head_key_{dinosaur_head_id}"', normal_html)

        insect_html = client.get("/build?frame_type=insect").get_data(as_text=True)
        self.assertIn(f'id="head_key_{insect_head_id}"', insect_html)
        self.assertNotIn(f'id="head_key_{normal_head_id}"', insect_html)
        self.assertNotIn(f'id="head_key_{dinosaur_head_id}"', insect_html)
        self.assertIn("昆虫系パーツで組み立てる特殊フレームです。", insect_html)

        dinosaur_html = client.get("/build?frame_type=dinosaur").get_data(as_text=True)
        self.assertIn(f'id="head_key_{dinosaur_head_id}"', dinosaur_html)
        self.assertNotIn(f'id="head_key_{normal_head_id}"', dinosaur_html)
        self.assertNotIn(f'id="head_key_{insect_head_id}"', dinosaur_html)
        self.assertIn("恐竜型フレーム専用", dinosaur_html)

    def test_build_confirm_rejects_mixed_frames(self):
        normal_head_id = self._create_instance(self.normal_parts["HEAD"]["key"])
        insect_ids = {
            "r_arm_key": self._create_instance("right_arm_kabuto"),
            "l_arm_key": self._create_instance("left_arm_kabuto"),
            "legs_key": self._create_instance("legs_kabuto"),
        }
        client = self._client()
        resp = client.post(
            "/build/confirm",
            data={
                "robot_name": "MixedBot",
                "frame_type": "normal",
                "head_key": str(normal_head_id),
                **{key: str(value) for key, value in insect_ids.items()},
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            "このパーツ同士はフレームが異なるため編成できません。",
            resp.get_data(as_text=True),
        )

    def test_build_confirm_allows_dinosaur_mixed_series(self):
        dinosaur_ids = {
            "head_key": self._create_instance("head_n_dino_tyranno"),
            "r_arm_key": self._create_instance("right_arm_n_dino_spino"),
            "l_arm_key": self._create_instance("left_arm_n_dino_tricera"),
            "legs_key": self._create_instance("legs_n_dino_raptor"),
        }
        client = self._client()
        resp = client.post(
            "/build/confirm",
            data={
                "robot_name": "DinoMixBot",
                "frame_type": "dinosaur",
                **{key: str(value) for key, value in dinosaur_ids.items()},
            },
            follow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303))
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT frame_type, composed_image_path, icon_32_path FROM robot_instances WHERE user_id = ? AND name = ? ORDER BY id DESC LIMIT 1",
                (self.user_id, "DinoMixBot"),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["frame_type"], "dinosaur")
            self.assertTrue(row["composed_image_path"])
            self.assertTrue(row["icon_32_path"])

    def test_build_confirm_rejects_dinosaur_standard_mix(self):
        normal_head_id = self._create_instance(self.normal_parts["HEAD"]["key"])
        dinosaur_ids = {
            "r_arm_key": self._create_instance("right_arm_n_dino_tyranno"),
            "l_arm_key": self._create_instance("left_arm_n_dino_tyranno"),
            "legs_key": self._create_instance("legs_n_dino_tyranno"),
        }
        client = self._client()
        resp = client.post(
            "/build/confirm",
            data={
                "robot_name": "BadDinoMix",
                "frame_type": "dinosaur",
                "head_key": str(normal_head_id),
                **{key: str(value) for key, value in dinosaur_ids.items()},
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("このパーツ同士はフレームが異なるため編成できません。", html)
        self.assertIn("恐竜型パーツは恐竜型どうしで編成してください。", html)

    def test_insect_build_generates_robot_and_icon_assets(self):
        insect_ids = {
            "head_key": self._create_instance("head_kabuto"),
            "r_arm_key": self._create_instance("right_arm_kabuto"),
            "l_arm_key": self._create_instance("left_arm_kabuto"),
            "legs_key": self._create_instance("legs_kabuto"),
        }
        client = self._client()
        resp = client.post(
            "/build/confirm",
            data={
                "robot_name": "InsectBot",
                "frame_type": "insect",
                **{key: str(value) for key, value in insect_ids.items()},
            },
            follow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303))
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT frame_type, composed_image_path, icon_32_path FROM robot_instances WHERE user_id = ? AND name = ? ORDER BY id DESC LIMIT 1",
                (self.user_id, "InsectBot"),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["frame_type"], "insect")
            self.assertTrue(row["composed_image_path"])
            self.assertTrue(row["icon_32_path"])

    def test_parts_page_shows_frame_filter_and_label(self):
        self._create_instance("head_kabuto")
        html = self._client().get("/parts?frame_type=insect").get_data(as_text=True)
        self.assertIn("すべて", html)
        self.assertIn("通常型", html)
        self.assertIn("虫型", html)
        self.assertIn("恐竜型", html)
        self.assertIn("フレーム：虫型", html)
        self.assertIn("剛角ヘッド", html)
        self.assertIn("シリーズ：カブト", html)

    def test_robot_maintenance_rejects_cross_frame_swap(self):
        insect_head_id = self._create_instance("head_kabuto")
        client = self._client()
        resp = client.post(
            f"/robots/{self.robot_id}/maintenance",
            data={"slot": "HEAD", "part_instance_id": str(insect_head_id)},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("選択したパーツのフレームタイプが合っていません。", resp.get_data(as_text=True))

    def test_strengthen_r_assist_does_not_use_cross_frame_n_materials(self):
        insect_r_part = self._insert_custom_part(
            key="head_r_frame_guard",
            part_type="HEAD",
            rarity="R",
            frame_type="insect",
            series="insect_kabuto",
            display_name="虫型Rヘッド試作",
        )
        base_id = self._create_instance(insect_r_part["key"])
        self._create_instance(self.normal_parts["HEAD"]["key"])
        self._create_instance(self.normal_parts["HEAD"]["key"])
        with game_app.app.app_context():
            db = game_app.get_db()
            result = game_app._strengthen_parts_selected(db, self.user_id, base_id)
            self.assertFalse(result["ok"])
            self.assertIn("対応N素材2個", result["message"])

    def test_evolve_rejects_cross_frame_insect_target_with_friendly_error(self):
        source_part = self._insert_custom_part(
            key="head_n_framebug",
            part_type="HEAD",
            rarity="N",
            frame_type="insect",
            series="insect_kabuto",
            display_name="虫型Nヘッド試作",
        )
        self._insert_custom_part(
            key="head_r_framebug",
            part_type="HEAD",
            rarity="R",
            frame_type="normal",
            series="S1",
            display_name="通常型Rヘッド試作",
        )
        source_id = self._create_instance(source_part["key"])
        self._grant_evolution_core()
        resp = self._client().post(
            "/parts/evolve",
            data={"part_instance_id": str(source_id)},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("進化先のフレームタイプが一致しません。", resp.get_data(as_text=True))

    def test_evolve_candidates_show_insect_series_for_admin(self):
        insect_id = self._create_instance("head_kabuto")
        self._grant_evolution_core()
        html = self._client().get("/parts/evolve").get_data(as_text=True)
        self.assertIn(f'value="{insect_id}"', html)
        self.assertIn("豪角ヘッド", html)
        self.assertNotIn("Rカブトヘッド", html)


if __name__ == "__main__":
    unittest.main()

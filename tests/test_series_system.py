import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class SeriesSystemTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 0, 0, 0, 5)
                """,
                ("series_tester", "x", now),
            )
            self.user_id = int(
                db.execute("SELECT id FROM users WHERE username = ?", ("series_tester",)).fetchone()["id"]
            )
            game_app.initialize_new_user(db, self.user_id)
            self.robot_id = int(
                db.execute("SELECT active_robot_id FROM users WHERE id = ?", (self.user_id,)).fetchone()["active_robot_id"]
            )
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "series_tester"
        return client

    def test_series_master_seeded_and_part_mapping_applied(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(db.execute("SELECT COUNT(*) AS c FROM series_master").fetchone()["c"])
            self.assertGreaterEqual(count, 7)
            row = db.execute(
                """
                SELECT rp.series, rp.image_path, sm.frame_type, sm.max_rarity, sm.can_evolve
                FROM robot_parts rp
                LEFT JOIN series_master sm ON sm.series_key = rp.series
                WHERE rp.key = 'head_kabuto'
                """
            ).fetchone()
            self.assertEqual(row["series"], "insect_kabuto")
            self.assertEqual(row["image_path"], "parts/head/head_kabuto.png")
            self.assertEqual(row["frame_type"], "insect")
            self.assertEqual(row["max_rarity"], "R")
            self.assertEqual(int(row["can_evolve"]), 1)

    def test_insect_r_parts_seeded_once_with_existing_assets(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            rows = db.execute(
                """
                SELECT key, part_type, image_path, rarity, series, frame_type, series_key, display_name_ja
                FROM robot_parts
                WHERE UPPER(COALESCE(rarity, 'N')) = 'R'
                  AND COALESCE(frame_type, 'normal') = 'insect'
                ORDER BY key ASC
                """
            ).fetchall()
            self.assertEqual(len(rows), 28)
            keys = {row["key"] for row in rows}
            for part in game_app.INSECT_R_PART_DEFINITIONS:
                self.assertIn(part["key"], keys)
            for row in rows:
                self.assertTrue(str(row["series"]).startswith("insect_"))
                self.assertEqual(row["series"], row["series_key"])
                self.assertEqual(row["rarity"], "R")
                self.assertEqual(row["frame_type"], "insect")
                self.assertTrue(str(row["display_name_ja"]).strip())
                self.assertNotIn("Rカブト", str(row["display_name_ja"]))
                self.assertNotIn("Rクワガタ", str(row["display_name_ja"]))
                self.assertNotIn("Rチョウ", str(row["display_name_ja"]))
                full_path = os.path.join(game_app.ASSET_ROOT, row["image_path"])
                self.assertTrue(os.path.exists(full_path), row["image_path"])

            game_app._sync_series_catalog(db)
            db.commit()
            count_after = int(
                db.execute(
                    """
                    SELECT COUNT(*) AS c
                    FROM robot_parts
                    WHERE UPPER(COALESCE(rarity, 'N')) = 'R'
                      AND COALESCE(frame_type, 'normal') = 'insect'
                    """
                ).fetchone()["c"]
            )
            self.assertEqual(count_after, 28)

    def test_insect_r_part_display_names_match_upgrade_names(self):
        expected = {
            "head_r_kabuto": "豪角ヘッド",
            "right_arm_r_kabuto": "重甲キャノン",
            "left_arm_r_kabuto": "鋼殻シールド",
            "legs_r_kabuto": "剛脚レッグ",
            "head_r_kuwagata": "双牙ヘッド",
            "right_arm_r_kuwagata": "紅牙ブレード",
            "left_arm_r_kuwagata": "顎砕クラッシャー",
            "legs_r_kuwagata": "剛斬脚フレーム",
            "head_r_batta": "飛躍ヘッド",
            "right_arm_r_batta": "跳撃ランサー",
            "left_arm_r_batta": "翡翠ガード",
            "legs_r_batta": "疾跳フレーム",
            "head_r_scorpion": "鋭蠍ヘッド",
            "right_arm_r_scorpion": "猛毒クロー",
            "left_arm_r_scorpion": "蠍甲ガード",
            "legs_r_scorpion": "蠍尾レッグ",
            "head_r_bee": "雷蜂ヘッド",
            "right_arm_r_bee": "雷針ランス",
            "left_arm_r_bee": "蜂紋ガード",
            "legs_r_bee": "空襲レッグ",
            "head_r_ant": "重工兵ヘッド",
            "right_arm_r_ant": "重機バスター",
            "left_arm_r_ant": "重工シールド",
            "legs_r_ant": "重六脚フレーム",
            "head_r_butterfly": "幻彩ヘッド",
            "right_arm_r_butterfly": "幻彩ブレード",
            "left_arm_r_butterfly": "幻彩シールド",
            "legs_r_butterfly": "幻舞レッグ",
        }
        with game_app.app.app_context():
            db = game_app.get_db()
            rows = db.execute(
                """
                SELECT key, display_name_ja, image_path, rarity, part_type
                FROM robot_parts
                WHERE key IN ({})
                """.format(",".join(["?"] * len(expected))),
                tuple(expected.keys()),
            ).fetchall()
            self.assertEqual(len(rows), 28)
            by_key = {row["key"]: row for row in rows}
            for part_key, display_name in expected.items():
                row = by_key[part_key]
                self.assertEqual(row["display_name_ja"], display_name)
                self.assertEqual(str(row["rarity"]).upper(), "R")
                self.assertIn(row["part_type"], {"HEAD", "RIGHT_ARM", "LEFT_ARM", "LEGS"})
                self.assertTrue(os.path.exists(os.path.join(game_app.ASSET_ROOT, row["image_path"])))

    def test_insect_r_names_do_not_match_same_series_n_names(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            for part in game_app.INSECT_R_PART_DEFINITIONS:
                source = db.execute(
                    """
                    SELECT display_name_ja, part_type, series_key
                    FROM robot_parts
                    WHERE key = ?
                    """,
                    (part["source_key"],),
                ).fetchone()
                target = db.execute(
                    """
                    SELECT display_name_ja, part_type, series_key
                    FROM robot_parts
                    WHERE key = ?
                    """,
                    (part["key"],),
                ).fetchone()
                self.assertIsNotNone(source, part["source_key"])
                self.assertIsNotNone(target, part["key"])
                self.assertEqual(source["part_type"], target["part_type"])
                self.assertEqual(source["series_key"], target["series_key"])
                self.assertTrue(str(target["display_name_ja"]).strip())
                self.assertNotEqual(
                    str(source["display_name_ja"]).strip(),
                    str(target["display_name_ja"]).strip(),
                    part["key"],
                )

    def test_insect_r_display_name_sync_updates_existing_db_only_name(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            before = db.execute(
                """
                SELECT key, series, image_path, rarity, element
                FROM robot_parts
                WHERE key = 'head_r_kabuto'
                """
            ).fetchone()
            db.execute(
                "UPDATE robot_parts SET display_name_ja = ? WHERE key = ?",
                ("Rカブトヘッド", "head_r_kabuto"),
            )
            game_app._sync_series_catalog(db)
            after = db.execute(
                """
                SELECT key, display_name_ja, series, image_path, rarity, element
                FROM robot_parts
                WHERE key = 'head_r_kabuto'
                """
            ).fetchone()
            self.assertEqual(after["display_name_ja"], "豪角ヘッド")
            self.assertEqual(after["series"], before["series"])
            self.assertEqual(after["image_path"], before["image_path"])
            self.assertEqual(after["rarity"], before["rarity"])
            self.assertEqual(after["element"], before["element"])

    def test_insect_n_to_r_mapping_exists_for_all_series_slots(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            for part in game_app.INSECT_R_PART_DEFINITIONS:
                source = db.execute("SELECT key FROM robot_parts WHERE key = ?", (part["source_key"],)).fetchone()
                target = db.execute("SELECT key, rarity, frame_type FROM robot_parts WHERE key = ?", (part["key"],)).fetchone()
                self.assertIsNotNone(source, part["source_key"])
                self.assertIsNotNone(target, part["key"])
                self.assertEqual(game_app.resolve_evolved_part_key(part["source_key"]), part["key"])
                self.assertEqual(str(target["rarity"]).upper(), "R")
                self.assertEqual(str(target["frame_type"]), "insect")

    def test_build_and_strengthen_pages_show_insect_r_parts(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("DELETE FROM part_instances WHERE user_id = ?", (self.user_id,))
            ids = {}
            for slot, key in {
                "head": "head_r_kabuto",
                "r_arm": "right_arm_r_kabuto",
                "l_arm": "left_arm_r_kabuto",
                "legs": "legs_r_kabuto",
            }.items():
                part = game_app._get_part_by_key(db, key)
                ids[slot] = game_app._create_part_instance_from_master(
                    db,
                    self.user_id,
                    part,
                    plus=0,
                    status="inventory",
                )
            for _ in range(3):
                game_app._create_part_instance_from_master(
                    db,
                    self.user_id,
                    game_app._get_part_by_key(db, "head_r_kabuto"),
                    plus=0,
                    status="inventory",
                )
            db.commit()

        client = self._client()
        parts_resp = client.get("/parts")
        self.assertEqual(parts_resp.status_code, 200)
        parts_html = parts_resp.get_data(as_text=True)
        self.assertIn("豪角ヘッド", parts_html)
        self.assertNotIn("Rカブトヘッド", parts_html)

        build_resp = client.get("/build?mode=new&frame_type=insect")
        self.assertEqual(build_resp.status_code, 200)
        build_html = build_resp.get_data(as_text=True)
        self.assertIn("豪角ヘッド", build_html)
        self.assertIn("重甲キャノン", build_html)
        self.assertIn("鋼殻シールド", build_html)
        self.assertIn("剛脚レッグ", build_html)

        confirm_resp = client.post(
            "/build/confirm",
            data={
                "mode": "new",
                "frame_type": "insect",
                "robot_name": "Kabuto R Test",
                "head_key": str(ids["head"]),
                "r_arm_key": str(ids["r_arm"]),
                "l_arm_key": str(ids["l_arm"]),
                "legs_key": str(ids["legs"]),
            },
            follow_redirects=False,
        )
        self.assertEqual(confirm_resp.status_code, 302)

        strengthen_resp = client.get("/parts/strengthen?mode=select&part_type=HEAD&rarity=R")
        self.assertEqual(strengthen_resp.status_code, 200)
        strengthen_html = strengthen_resp.get_data(as_text=True)
        self.assertIn("豪角ヘッド", strengthen_html)
        self.assertNotIn("Rカブトヘッド", strengthen_html)

    def test_insect_r_release_flag_defaults_to_admin_only(self):
        old_bypass = game_app.app.config.get("BYPASS_RELEASE_GATES_IN_TESTS", True)
        game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = False
        try:
            with game_app.app.app_context():
                db = game_app.get_db()
                row = db.execute(
                    "SELECT is_public FROM release_flags WHERE key = ?",
                    (game_app.INSECT_R_PARTS_FEATURE_KEY,),
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(int(row["is_public"] or 0), 0)
                self.assertFalse(game_app._insect_r_parts_open_for_viewer(db, user_id=self.user_id))
                db.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (self.user_id,))
                db.commit()
                self.assertTrue(game_app._insect_r_parts_open_for_viewer(db, user_id=self.user_id))
        finally:
            game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = old_bypass

    def test_insect_part_display_names_match_robot_motifs(self):
        expected = {
            "head_kuwagata": "双顎ヘッド",
            "right_arm_kuwagata": "紅顎ブレード",
            "left_arm_kuwagata": "顎砲クラッシャー",
            "legs_kuwagata": "斬脚フレーム",
            "head_bee": "針蜂ヘッド",
            "right_arm_bee": "スティングランス",
            "left_arm_bee": "蜂紋シールド",
            "legs_bee": "空戦レッグ",
            "head_butterfly": "幻蝶ヘッド",
            "right_arm_butterfly": "幻翼ブレード",
            "left_arm_butterfly": "幻翼シールド",
            "legs_butterfly": "幻蝶レッグ",
            "head_batta": "跳躍ヘッド",
            "right_arm_batta": "跳撃ランス",
            "left_arm_batta": "翡翠シールド",
            "legs_batta": "跳脚フレーム",
            "head_kabuto": "剛角ヘッド",
            "right_arm_kabuto": "三連キャノン",
            "left_arm_kabuto": "甲殻シールド",
            "legs_kabuto": "重甲レッグ",
            "head_ant": "工兵ヘッド",
            "right_arm_ant": "重機キャノン",
            "left_arm_ant": "工兵シールド",
            "legs_ant": "六脚フレーム",
            "head_scorpion": "毒蠍ヘッド",
            "right_arm_scorpion": "毒爪クロー",
            "left_arm_scorpion": "蠍甲シールド",
            "legs_scorpion": "蠍脚フレーム",
        }
        with game_app.app.app_context():
            db = game_app.get_db()
            rows = db.execute(
                """
                SELECT key, display_name_ja, series, image_path, rarity, element
                FROM robot_parts
                WHERE key IN ({})
                """.format(",".join(["?"] * len(expected))),
                tuple(expected.keys()),
            ).fetchall()
            self.assertEqual(len(rows), len(expected))
            by_key = {row["key"]: row for row in rows}
            for part_key, display_name in expected.items():
                row = by_key[part_key]
                self.assertEqual(row["display_name_ja"], display_name)
                self.assertTrue(str(row["series"]).startswith("insect_"))
                self.assertEqual(row["rarity"], "N")
                self.assertEqual(row["element"], "NORMAL")
                self.assertIn(part_key, row["image_path"])

    def test_insect_part_display_name_sync_updates_existing_db_only_name(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            before = db.execute(
                """
                SELECT key, series, image_path, rarity, element
                FROM robot_parts
                WHERE key = 'right_arm_kabuto'
                """
            ).fetchone()
            db.execute(
                "UPDATE robot_parts SET display_name_ja = ? WHERE key = ?",
                ("カブト右腕", "right_arm_kabuto"),
            )
            changed = game_app._sync_insect_part_display_names(db)
            after = db.execute(
                """
                SELECT key, display_name_ja, series, image_path, rarity, element
                FROM robot_parts
                WHERE key = 'right_arm_kabuto'
                """
            ).fetchone()
            self.assertEqual(changed, 1)
            self.assertEqual(after["display_name_ja"], "三連キャノン")
            self.assertEqual(after["series"], before["series"])
            self.assertEqual(after["image_path"], before["image_path"])
            self.assertEqual(after["rarity"], before["rarity"])
            self.assertEqual(after["element"], before["element"])

    def test_series_release_gate_defaults_to_admin_only(self):
        old_bypass = game_app.app.config.get("BYPASS_RELEASE_GATES_IN_TESTS", True)
        game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = False
        try:
            with game_app.app.app_context():
                db = game_app.get_db()
                self.assertFalse(game_app._series_system_enabled_for_user(db, user_id=self.user_id))
                db.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (self.user_id,))
                db.commit()
                self.assertTrue(game_app._series_system_enabled_for_user(db, user_id=self.user_id))
        finally:
            game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = old_bypass

    def test_robot_stats_apply_series_bonus_for_equipped_kabuto_set(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            keys = {
                "head": "head_kabuto",
                "r_arm": "right_arm_kabuto",
                "l_arm": "left_arm_kabuto",
                "legs": "legs_kabuto",
            }
            part_instance_ids = {}
            for slot, key in keys.items():
                part = game_app._get_part_by_key(db, key)
                part_instance_ids[slot] = game_app._create_part_instance_from_master(
                    db,
                    self.user_id,
                    part,
                    plus=0,
                    status="inventory",
                )
            game_app._equip_part_instances_on_robot(db, self.robot_id, part_instance_ids)
            db.execute(
                """
                UPDATE robot_instance_parts
                SET head_key = ?, r_arm_key = ?, l_arm_key = ?, legs_key = ?
                WHERE robot_instance_id = ?
                """,
                (keys["head"], keys["r_arm"], keys["l_arm"], keys["legs"], self.robot_id),
            )
            db.commit()

            stat_obj = game_app._compute_robot_stats_for_instance(db, self.robot_id)
            self.assertEqual(stat_obj["series_counts"]["insect_kabuto"], 4)
            self.assertTrue(any(row["stat_key"] == "def" for row in stat_obj["series_bonus"]))
            self.assertTrue(any(row["stat_key"] == "hp" for row in stat_obj["series_bonus"]))

    def test_build_and_robot_detail_show_series_section(self):
        client = self._client()
        build_resp = client.get("/build")
        self.assertEqual(build_resp.status_code, 200)
        build_html = build_resp.get_data(as_text=True)
        self.assertIn("シリーズ効果:", build_html)
        self.assertIn("同シリーズ 2部位 / 4部位で発動", build_html)

        detail_resp = client.get(f"/robots/{self.robot_id}")
        self.assertEqual(detail_resp.status_code, 200)
        detail_html = detail_resp.get_data(as_text=True)
        self.assertIn("シリーズ効果:", detail_html)


if __name__ == "__main__":
    unittest.main()

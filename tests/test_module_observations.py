import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class ModuleObservationTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 0, 0, 1)
                """,
                ("observer", "x", now),
            )
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 0, 0, 1)
                """,
                ("other_observer", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = 'observer'").fetchone()["id"])
            self.other_user_id = int(db.execute("SELECT id FROM users WHERE username = 'other_observer'").fetchone()["id"])
            db.commit()
        self._seq = 0

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self, user_id=None, username="observer"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id or self.user_id)
            session["username"] = username
        return client

    def _record(self, *, user_id=None, lineage_key="volt", lineage_label="ヴォルト", generation=1, created_at=None, provenance_quality="full", inputs=None):
        self._seq += 1
        user_id = int(user_id or self.user_id)
        created_at = int(created_at or (time.time() + self._seq))
        snapshot = {
            "name": f"{lineage_label}観測{self._seq}",
            "generation": int(generation),
            "generation_label": game_app._module_generation_label(generation),
            "primary_lineage_key": lineage_key,
            "primary_lineage_label": lineage_label,
            "stat_chips": [{"text": "攻撃 +1", "tone": "positive"}],
        }
        with game_app.app.app_context():
            db = game_app.get_db()
            cur = db.execute(
                """
                INSERT INTO module_fusion_records (
                    user_id, result_module_instance_id, result_module_key, result_name, result_generation,
                    result_primary_lineage_key, result_primary_lineage_label, result_snapshot_json,
                    provenance_quality, provenance_version, request_id, created_at
                )
                VALUES (?, ?, 'synthesized_module', ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    user_id,
                    70000 + self._seq,
                    f"{lineage_label}観測{self._seq}",
                    int(generation),
                    lineage_key,
                    lineage_label,
                    json.dumps(snapshot, ensure_ascii=False),
                    provenance_quality,
                    f"obs-{self._seq}",
                    created_at,
                ),
            )
            record_id = int(cur.lastrowid)
            for index, item in enumerate(inputs or (), start=1):
                db.execute(
                    """
                    INSERT INTO module_fusion_inputs (
                        fusion_record_id, input_index, source_module_instance_id, source_module_key,
                        source_name, source_generation, source_primary_lineage_key,
                        source_primary_lineage_label, source_snapshot_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_id,
                        index,
                        80000 + self._seq * 10 + index,
                        f"input_{index}",
                        item["name"],
                        int(item["generation"]),
                        item["lineage_key"],
                        item["lineage_label"],
                        json.dumps({"name": item["name"]}, ensure_ascii=False),
                        created_at,
                    ),
                )
            db.commit()
            return record_id

    def test_observation_atlas_counts_result_lineage_only(self):
        base = int(time.time()) - 1000
        self._record(lineage_key="volt", lineage_label="ヴォルト", generation=2, created_at=base)
        self._record(lineage_key="stable", lineage_label="安定", generation=1, created_at=base + 10, inputs=[
            {"name": "ヴォルト素材", "generation": 1, "lineage_key": "volt", "lineage_label": "ヴォルト"},
        ])
        self._record(lineage_key="volt", lineage_label="ヴォルト", generation=4, created_at=base + 20)
        self._record(lineage_key="volt", lineage_label="ヴォルト", generation=1, created_at=base + 30)
        self._record(lineage_key="", lineage_label="", generation=9, created_at=base + 40, provenance_quality="partial")
        self._record(lineage_key="eden", lineage_label="エデン", generation=3, created_at=base + 50, provenance_quality="partial")
        self._record(user_id=self.other_user_id, lineage_key="volt", lineage_label="ヴォルト", generation=8, created_at=base + 60)

        html = self._client().get("/modules/research?tab=observations").get_data(as_text=True)
        self.assertIn("観測帳", html)
        self.assertIn("観測済み 3系統", html)
        self.assertIn("ヴォルト", html)
        self.assertIn("3回観測", html)
        self.assertIn("最高確認 第4世代", html)
        self.assertIn("安定", html)
        self.assertIn("1回観測", html)
        self.assertIn("エデン", html)
        self.assertNotIn("第8世代", html)
        for forbidden in ("観測率", "発現率", "成功率", "weight", "RNG", "seed", "おすすめ合成", "最適配合"):
            self.assertNotIn(forbidden, html)

        detail = self._client().get("/modules/research/observations/volt").get_data(as_text=True)
        self.assertIn("ヴォルト 観測帳", detail)
        self.assertIn("3回観測", detail)
        self.assertIn("最高確認 第4世代", detail)
        self.assertIn("ヴォルト素材", self._client().get("/modules/research/observations/stable").get_data(as_text=True))

    def test_observation_detail_paginates_and_note_is_private_and_escaped(self):
        for idx in range(21):
            self._record(lineage_key="volt", lineage_label="ヴォルト", generation=idx + 1)
        client = self._client()
        page = client.get("/modules/research/observations/volt").get_data(as_text=True)
        self.assertIn("次へ", page)
        resp = client.post(
            "/modules/research/observations/volt/note",
            data={"note_text": "<script>alert(1)</script>要検証"},
            follow_redirects=True,
        )
        html = resp.get_data(as_text=True)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;要検証", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            audit = db.execute(
                "SELECT event_type FROM world_events_log WHERE event_type = ? ORDER BY id DESC LIMIT 1",
                (game_app.AUDIT_EVENT_TYPES["MODULE_RESEARCH_NOTE_UPDATE"],),
            ).fetchone()
            self.assertIsNotNone(audit)

        other_html = self._client(self.other_user_id, "other_observer").get("/modules/research/observations/volt", follow_redirects=True).get_data(as_text=True)
        self.assertIn("観測記録が見つかりません", other_html)
        self.assertNotIn("要検証", other_html)

    def test_public_share_detail_does_not_expose_observation_atlas(self):
        record_id = self._record(lineage_key="volt", lineage_label="ヴォルト", generation=2, inputs=[
            {"name": "安定素材", "generation": 1, "lineage_key": "stable", "lineage_label": "安定"},
        ])
        self._client().post(f"/modules/research/{record_id}/share", data={"message": "共有用"})
        with game_app.app.app_context():
            db = game_app.get_db()
            share_id = int(db.execute("SELECT id FROM module_research_shares").fetchone()["id"])
        html = self._client(self.other_user_id, "other_observer").get(f"/modules/research/shares/{share_id}").get_data(as_text=True)
        self.assertIn("共有研究記録", html)
        self.assertIn("共有用", html)
        self.assertNotIn("観測帳で", html)
        self.assertNotIn("観測履歴を見る", html)


if __name__ == "__main__":
    unittest.main()

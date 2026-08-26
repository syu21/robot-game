import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class ModuleResearchShareTests(unittest.TestCase):
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
                ("share_user", "x", now),
            )
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 0, 0, 1)
                """,
                ("other_user", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = 'share_user'").fetchone()["id"])
            self.other_user_id = int(db.execute("SELECT id FROM users WHERE username = 'other_user'").fetchone()["id"])
            db.commit()
            self._record_seq = 0

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self, user_id=None, username="share_user"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = user_id or self.user_id
            session["username"] = username
        return client

    def _create_fusion_record(self, *, user_id=None, provenance_quality="full", result_name="ヴォルト第四世代"):
        user_id = int(user_id or self.user_id)
        self._record_seq += 1
        now = int(time.time()) - 120
        result_snapshot = {
            "name": result_name,
            "generation": 4,
            "generation_label": "第4世代",
            "primary_lineage_key": "volt",
            "primary_lineage_label": "ヴォルト",
            "family_label": "安定重装",
            "family_label_compact": "安定重装",
            "trait_label": "先制出力",
            "usage_labels": ["高速戦"],
            "stat_chips": [{"text": "攻撃 +7", "tone": "up"}, {"text": "素早さ +9", "tone": "up"}],
            "bonuses": {"hp_bonus": 3, "atk_bonus": 7, "def_bonus": -1, "spd_bonus": 9, "acc_bonus": -1, "cri_bonus": 1},
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
                VALUES (?, ?, ?, ?, 4, 'volt', 'ヴォルト', ?, ?, 1, '', ?)
                """,
                (
                    user_id,
                    9000 + self._record_seq,
                    game_app.RESEARCH_MODULE_SYNTHESIS_KEY,
                    result_name,
                    json.dumps(result_snapshot, ensure_ascii=False),
                    provenance_quality,
                    now,
                ),
            )
            record_id = int(cur.lastrowid)
            for index, (name, generation, lineage) in enumerate(
                [("安定重装モジュール", 3, "安定重装"), ("ヴォルト", 1, "ヴォルト")],
                start=1,
            ):
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
                        8000 + index,
                        f"input_{index}",
                        name,
                        generation,
                        lineage.lower(),
                        lineage,
                        json.dumps({"name": name}, ensure_ascii=False),
                        now,
                    ),
                )
            db.commit()
            return record_id

    def test_share_creates_global_room_card_with_frozen_snapshot(self):
        record_id = self._create_fusion_record(result_name="共有時の研究名")
        resp = self._client().post(
            f"/modules/research/{record_id}/share",
            data={"message": "これって先祖返り？"},
        )
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            share = db.execute("SELECT * FROM module_research_shares").fetchone()
            self.assertIsNotNone(share)
            self.assertEqual(share["room_key"], "global_room")
            snapshot = json.loads(share["snapshot_json"])
            self.assertEqual(snapshot["result"]["display_name"], "共有時の研究名")
            db.execute(
                "UPDATE module_fusion_records SET result_name = ? WHERE id = ?",
                ("あとから変えた名前", record_id),
            )
            db.commit()
            message = db.execute("SELECT room_key, message FROM chat_messages WHERE id = ?", (share["chat_message_id"],)).fetchone()
            self.assertEqual(message["room_key"], "global_room")
            self.assertEqual(message["message"], "これって先祖返り？")

        page = self._client().get("/comms/rooms?room=global_room")
        html = page.get_data(as_text=True)
        self.assertIn("研究成果", html)
        self.assertIn("共有時の研究名", html)
        self.assertIn("これって先祖返り？", html)
        self.assertNotIn("あとから変えた名前", html)

    def test_share_rejects_other_user_and_legacy_records(self):
        other_record_id = self._create_fusion_record(user_id=self.other_user_id)
        legacy_record_id = self._create_fusion_record(provenance_quality="partial")
        client = self._client()
        self.assertEqual(client.post(f"/modules/research/{other_record_id}/share", data={"message": "x"}).status_code, 302)
        self.assertEqual(client.post(f"/modules/research/{legacy_record_id}/share", data={"message": "x"}).status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(db.execute("SELECT COUNT(*) AS c FROM module_research_shares").fetchone()["c"] or 0)
            self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()

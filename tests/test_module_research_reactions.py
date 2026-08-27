import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class ModuleResearchReactionTests(unittest.TestCase):
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
            for username, is_admin in (("owner", 0), ("viewer", 0), ("admin", 1)):
                db.execute(
                    """
                    INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                    VALUES (?, ?, ?, ?, 0, 1)
                    """,
                    (username, "x", now, is_admin),
                )
            self.owner_id = int(db.execute("SELECT id FROM users WHERE username = 'owner'").fetchone()["id"])
            self.viewer_id = int(db.execute("SELECT id FROM users WHERE username = 'viewer'").fetchone()["id"])
            self.admin_id = int(db.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()["id"])
            db.commit()
        self._seq = 0

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self, user_id, username):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id)
            session["username"] = username
        return client

    def _share(self, *, owner_id=None, title="共有研究", created_offset=0, deleted=False):
        self._seq += 1
        owner_id = int(owner_id or self.owner_id)
        now = int(time.time()) + int(created_offset)
        snapshot = {
            "share_version": 1,
            "fusion_record_id": 60000 + self._seq,
            "fusion_created_at": now,
            "result": {
                "display_name": title,
                "generation": 4,
                "generation_label": "第4世代",
                "primary_lineage_key": "volt",
                "primary_lineage_label": "ヴォルト",
                "family_label_compact": "安定重装",
                "stat_chips": [{"text": "攻撃 +7", "tone": "positive"}],
                "bonuses": {"atk_bonus": 7},
            },
            "inputs": [
                {"display_name": "安定素材", "generation": 3, "generation_label": "第3世代", "lineage_key": "stable", "lineage_label": "安定"},
                {"display_name": "ヴォルト素材", "generation": 1, "generation_label": "初代", "lineage_key": "volt", "lineage_label": "ヴォルト"},
            ],
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
                VALUES (?, ?, 'synthesized_module', ?, 4, 'volt', 'ヴォルト', ?, 'full', 1, ?, ?)
                """,
                (
                    owner_id,
                    61000 + self._seq,
                    title,
                    json.dumps(snapshot["result"], ensure_ascii=False),
                    f"react-{self._seq}",
                    now,
                ),
            )
            record_id = int(cur.lastrowid)
            chat_id = game_app._insert_chat_message(
                db,
                user_id=owner_id,
                username="owner",
                message="見てほしい研究",
                room_key="global_room",
            )
            share_cur = db.execute(
                """
                INSERT INTO module_research_shares (
                    chat_message_id, fusion_record_id, user_id, room_key, snapshot_json,
                    share_version, provenance_version, created_at
                )
                VALUES (?, ?, ?, 'global_room', ?, 1, 1, ?)
                """,
                (chat_id, record_id, owner_id, json.dumps(snapshot, ensure_ascii=False), now),
            )
            if deleted:
                db.execute("UPDATE chat_messages SET deleted_at = ? WHERE id = ?", (game_app.now_str(), chat_id))
            db.commit()
            return int(share_cur.lastrowid), int(chat_id), int(record_id)

    def test_reactions_toggle_and_allow_two_types_without_duplicates(self):
        share_id, _chat_id, _record_id = self._share()
        client = self._client(self.viewer_id, "viewer")
        first = client.post(
            f"/modules/research/shares/{share_id}/react",
            data={"reaction_type": "interesting", "surface": "module_research_public"},
        )
        self.assertEqual(first.status_code, 302)
        second = client.post(
            f"/modules/research/shares/{share_id}/react",
            data={"reaction_type": "interesting", "surface": "module_research_public"},
        )
        self.assertEqual(second.status_code, 302)
        client.post(
            f"/modules/research/shares/{share_id}/react",
            data={"reaction_type": "replicate", "surface": "module_research_public"},
        )
        with game_app.app.app_context():
            db = game_app.get_db()
            rows = db.execute("SELECT reaction_type FROM module_research_share_reactions ORDER BY reaction_type").fetchall()
            self.assertEqual([row["reaction_type"] for row in rows], ["replicate"])
            audits = db.execute(
                """
                SELECT payload_json
                FROM world_events_log
                WHERE event_type = ?
                ORDER BY id ASC
                """,
                (game_app.AUDIT_EVENT_TYPES["MODULE_RESEARCH_REACT"],),
            ).fetchall()
            payloads = [json.loads(row["payload_json"]) for row in audits]
            self.assertEqual([payload["action"] for payload in payloads], ["add", "remove", "add"])
            self.assertEqual(payloads[-1]["reaction_type"], "replicate")

    def test_self_invalid_deleted_and_banned_reactions_are_rejected(self):
        share_id, chat_id, _record_id = self._share()
        owner = self._client(self.owner_id, "owner")
        self.assertEqual(owner.post(f"/modules/research/shares/{share_id}/react", data={"reaction_type": "interesting"}).status_code, 403)
        viewer = self._client(self.viewer_id, "viewer")
        self.assertEqual(viewer.post(f"/modules/research/shares/{share_id}/react", data={"reaction_type": "legendary"}).status_code, 400)
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE chat_messages SET deleted_at = ? WHERE id = ?", (game_app.now_str(), chat_id))
            db.commit()
        self.assertEqual(viewer.post(f"/modules/research/shares/{share_id}/react", data={"reaction_type": "interesting"}).status_code, 404)
        deleted_share_id, _deleted_chat_id, _ = self._share(deleted=True)
        self.assertEqual(viewer.get(f"/modules/research/shares/{deleted_share_id}").status_code, 404)

    def test_recent_research_uses_snapshot_latest_order_and_hides_deleted(self):
        old_share_id, _chat_id, _ = self._share(title="古い研究", created_offset=-100)
        new_share_id, _chat_id2, record_id = self._share(title="新しい研究", created_offset=100)
        self._share(title="削除済み研究", created_offset=200, deleted=True)
        client = self._client(self.viewer_id, "viewer")
        client.post(
            f"/modules/research/shares/{new_share_id}/react",
            data={"reaction_type": "interesting", "surface": "module_research_recent"},
        )
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE module_fusion_records SET result_name = ? WHERE id = ?", ("後から変えた名前", record_id))
            db.commit()
        html = client.get("/modules/research?tab=recent").get_data(as_text=True)
        self.assertIn("最近の研究", html)
        self.assertIn("新しい研究", html)
        self.assertIn("古い研究", html)
        self.assertLess(html.index("新しい研究"), html.index("古い研究"))
        self.assertNotIn("削除済み研究", html)
        self.assertNotIn("後から変えた名前", html)
        self.assertIn("✓ 気になる 1", html)
        self.assertNotIn("観測履歴を見る", html)
        self.assertIn(str(old_share_id), html)

    def test_reaction_does_not_trigger_chat_cooldown_and_admin_metrics_counts(self):
        share_id, _chat_id, record_id = self._share()
        viewer = self._client(self.viewer_id, "viewer")
        viewer.post(
            f"/modules/research/shares/{share_id}/react",
            data={"reaction_type": "replicate", "surface": "module_research_public"},
        )
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                INSERT INTO module_fusion_records (
                    user_id, result_module_instance_id, result_module_key, result_name, result_generation,
                    result_primary_lineage_key, result_primary_lineage_label, result_snapshot_json,
                    provenance_quality, provenance_version, request_id, created_at
                )
                VALUES (?, 69001, 'synthesized_module', '追試後合成', 1, 'stable', '安定', '{}', 'full', 1, 'after-react', ?)
                """,
                (self.viewer_id, int(time.time()) + 60),
            )
            db.commit()
        post = viewer.post(
            "/comms/rooms?room=global_room",
            data={"room_key": "global_room", "message": "リアクション後の通常投稿", "next": "/comms/rooms?room=global_room"},
            follow_redirects=True,
        )
        self.assertEqual(post.status_code, 200)
        self.assertIn("リアクション後の通常投稿", post.get_data(as_text=True))
        owner_html = self._client(self.owner_id, "owner").get("/modules/research").get_data(as_text=True)
        self.assertIn("会議室共有済み", owner_html)
        self.assertIn("追試したい 1", owner_html)
        admin_html = self._client(self.admin_id, "admin").get("/admin/metrics").get_data(as_text=True)
        self.assertIn("モジュール研究反応", admin_html)
        self.assertIn("追試反応後24h 合成", admin_html)
        self.assertIn("自分への反応", admin_html)


if __name__ == "__main__":
    unittest.main()

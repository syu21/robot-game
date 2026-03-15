import sqlite3
import unittest

from services.audit import audit_log


class AuditLogSmokeTest(unittest.TestCase):
    def test_insert_world_event_with_extended_columns(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute(
            """
            CREATE TABLE world_events_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT,
                user_id INTEGER,
                request_id TEXT,
                ip_hash TEXT,
                action_key TEXT,
                entity_type TEXT,
                entity_id INTEGER,
                delta_coins INTEGER,
                delta_count INTEGER
            )
            """
        )
        rid = audit_log(
            db,
            "audit.coin.delta",
            user_id=1,
            action_key="click",
            entity_type="user",
            entity_id=1,
            delta_coins=3,
            payload={"gain": 3},
            ip="127.0.0.1",
        )
        db.commit()
        self.assertTrue(rid)
        row = db.execute("SELECT * FROM world_events_log").fetchone()
        self.assertEqual(row["event_type"], "audit.coin.delta")
        self.assertEqual(row["delta_coins"], 3)
        self.assertEqual(row["user_id"], 1)


if __name__ == "__main__":
    unittest.main()

import sqlite3
import unittest

from constants import AUDIT_EVENT_TYPES
from services.lab_level import get_lab_rank_label, get_required_lab_exp, grant_lab_exp


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            lab_level INTEGER NOT NULL DEFAULT 1,
            lab_exp INTEGER NOT NULL DEFAULT 0,
            lab_total_exp INTEGER NOT NULL DEFAULT 0,
            lab_rank_label TEXT NOT NULL DEFAULT '見習い研究員',
            lab_level_updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE user_lab_exp_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action_key TEXT NOT NULL,
            exp_delta INTEGER NOT NULL,
            lab_level_before INTEGER NOT NULL,
            lab_level_after INTEGER NOT NULL,
            lab_exp_before INTEGER NOT NULL,
            lab_exp_after INTEGER NOT NULL,
            lab_total_exp_after INTEGER NOT NULL,
            source_entity_type TEXT,
            source_entity_id INTEGER,
            payload_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
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
    conn.execute("INSERT INTO users (id, username) VALUES (1, 'tester')")
    conn.commit()
    return conn


class LabLevelTests(unittest.TestCase):
    def test_required_exp_is_monotonic(self):
        values = [get_required_lab_exp(level) for level in range(1, 20)]
        self.assertEqual(values, sorted(values))
        self.assertGreater(values[-1], values[0])

    def test_grant_exp_records_history_and_audit(self):
        db = _db()
        result = grant_lab_exp(db, 1, "explore.end", 8, payload={"area_key": "layer_1"})
        self.assertEqual(result["exp_delta"], 8)
        self.assertFalse(result["leveled_up"])

        user = db.execute("SELECT * FROM users WHERE id = 1").fetchone()
        self.assertEqual(user["lab_exp"], 8)
        self.assertEqual(user["lab_total_exp"], 8)

        event_count = db.execute("SELECT COUNT(*) AS c FROM user_lab_exp_events").fetchone()["c"]
        self.assertEqual(event_count, 1)
        audit = db.execute("SELECT event_type FROM world_events_log").fetchall()
        self.assertEqual([row["event_type"] for row in audit], [AUDIT_EVENT_TYPES["LAB_LEVEL_EXP_GAIN"]])

    def test_level_up_and_rank_update(self):
        db = _db()
        result = grant_lab_exp(db, 1, "boss.defeat", get_required_lab_exp(1) + get_required_lab_exp(2) + 1)
        self.assertEqual(result["level_after"], 3)
        self.assertTrue(result["leveled_up"])
        self.assertEqual(result["rank_after"], "新米整備士")

        user = db.execute("SELECT lab_level, lab_rank_label FROM users WHERE id = 1").fetchone()
        self.assertEqual(user["lab_level"], 3)
        self.assertEqual(user["lab_rank_label"], "新米整備士")
        logs = [row["event_type"] for row in db.execute("SELECT event_type FROM world_events_log").fetchall()]
        self.assertIn(AUDIT_EVENT_TYPES["LAB_LEVEL_LEVEL_UP"], logs)

    def test_milestone_world_log(self):
        db = _db()
        total = sum(get_required_lab_exp(level) for level in range(1, 5))
        result = grant_lab_exp(db, 1, "backfill.initial", total)
        self.assertEqual(result["level_after"], 5)
        self.assertTrue(result["milestone"])
        self.assertEqual(get_lab_rank_label(5), "実験補助員")
        logs = [row["event_type"] for row in db.execute("SELECT event_type FROM world_events_log").fetchall()]
        self.assertIn(AUDIT_EVENT_TYPES["LAB_LEVEL_MILESTONE"], logs)


if __name__ == "__main__":
    unittest.main()

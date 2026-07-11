import os
import tempfile
import time
import unittest
from unittest import mock

import app as game_app
import init_db
from services.research_module_synthesis import synthesize_research_module
from services.module_traits import module_area_fit, synthesis_prediction


class ModuleResearchV2Tests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer, coins)
                VALUES (?, ?, ?, 1, 0, 5, 1000)
                """,
                ("module_v2", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("module_v2",)).fetchone()["id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "module_v2"
        return client

    def _grant_module(self, module_key):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            cur = db.execute(
                """
                INSERT INTO user_research_modules (user_id, module_key, status, created_at, updated_at)
                VALUES (?, ?, 'inventory', ?, ?)
                """,
                (self.user_id, module_key, now, now),
            )
            db.commit()
            return int(cur.lastrowid)

    def test_trait_columns_are_backward_compatible(self):
        module_id = self._grant_module("sniper_prototype")
        with game_app.app.app_context():
            db = game_app.get_db()
            cols = {row["name"] for row in db.execute("PRAGMA table_info(user_research_modules)").fetchall()}
            for col in ("trait_key", "trait_value", "trait_grade", "research_policy_key", "synthesis_generation"):
                self.assertIn(col, cols)
            module = game_app._research_module_instance_row(db, module_id, self.user_id)
            self.assertFalse(module["trait_label"])
            self.assertEqual(int(module["trait_value"] or 0), 0)

    def test_policy_prediction_reflects_material_tendency(self):
        module_a = {"atk_bonus": 9, "cri_bonus": 4, "def_bonus": 0, "hp_bonus": 0, "spd_bonus": 0, "acc_bonus": 1}
        module_b = {"atk_bonus": 7, "cri_bonus": 5, "def_bonus": 0, "hp_bonus": 0, "spd_bonus": 0, "acc_bonus": 1}
        prediction = synthesis_prediction([module_a, module_b], "trait")
        labels = [item["label"] for item in prediction["trait_candidates"]]
        self.assertEqual(prediction["policy_label"], "特性研究")
        self.assertIn("攻撃", prediction["ability_tendency"])
        self.assertIn("先制出力", labels)
        self.assertIn("臨界加速", labels)

    def test_trait_policy_can_create_trait_result(self):
        class FixedRng:
            def __init__(self):
                self.random_values = [0.50, 0.0]

            def random(self):
                return self.random_values.pop(0) if self.random_values else 0.0

            def randint(self, start, end):
                return min(max(5, int(start)), int(end))

            def choice(self, items):
                return list(items)[0]

            def sample(self, items, count):
                return list(items)[:count]

        module_a = {"family": "assault", "generation": 0, "atk_bonus": 10, "cri_bonus": 5}
        module_b = {"family": "berserk", "generation": 1, "atk_bonus": 8, "cri_bonus": 6}
        result = synthesize_research_module(module_a, module_b, rng=FixedRng(), research_policy_key="trait")
        self.assertEqual(result["research_policy_key"], "trait")
        self.assertEqual(result["trait"]["trait_key"], "opening_assault")
        self.assertGreaterEqual(int(result["trait"]["trait_value"]), 3)

    def test_synthesis_route_saves_policy_and_trait(self):
        module_a_id = self._grant_module("assault_prototype")
        module_b_id = self._grant_module("berserk_prototype")
        fake_result = {
            "result_type": "normal",
            "result_label": "研究成功",
            "synthesis_grade": "prototype",
            "synthesis_family": "assault_berserk",
            "generated_name_ja": "暴走突撃モジュール",
            "name_ja": "暴走突撃モジュール",
            "bonuses": {"hp_bonus": 0, "atk_bonus": 8, "def_bonus": 0, "spd_bonus": 0, "acc_bonus": 1, "cri_bonus": 5},
            "trait": {"trait_key": "opening_assault", "trait_value": 5, "trait_grade": "B"},
            "research_policy_key": "trait",
            "synthesis_score": 14,
            "generation": 1,
        }
        with mock.patch.object(game_app, "_roll_research_module_synthesis", return_value=fake_result):
            resp = self._client().post(
                "/modules/synthesis",
                data={"module_a_id": module_a_id, "module_b_id": module_b_id, "research_policy_key": "trait"},
            )
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("特性研究", html)
        self.assertIn("先制出力", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                """
                SELECT trait_key, trait_value, trait_grade, research_policy_key, synthesis_generation
                FROM user_research_modules
                WHERE user_id = ? AND module_key = 'synthesized_module'
                ORDER BY id DESC LIMIT 1
                """,
                (self.user_id,),
            ).fetchone()
            self.assertEqual(row["trait_key"], "opening_assault")
            self.assertEqual(int(row["trait_value"]), 5)
            self.assertEqual(row["trait_grade"], "B")
            self.assertEqual(row["research_policy_key"], "trait")
            self.assertEqual(int(row["synthesis_generation"]), 1)

    def test_area_fit_uses_trait_without_extra_bonus(self):
        fit = module_area_fit({"trait_key": "precision_retry", "trait_value": 6, "acc_bonus": 0}, "layer_4_haze")
        self.assertEqual(fit["label"], "良好")
        self.assertIn("命中", fit["message"])


if __name__ == "__main__":
    unittest.main()

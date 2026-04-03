import json
import os
import tempfile
import time
import unittest
from types import SimpleNamespace

from werkzeug.security import generate_password_hash

import app as game_app
import init_db


class _FakeStripeSignatureError(Exception):
    pass


class _FakeStripeSessionAPI:
    last_kwargs = None

    @classmethod
    def create(cls, **kwargs):
        cls.last_kwargs = kwargs
        product_key = str((kwargs.get("metadata") or {}).get("product_key") or "")
        session_id = "cs_test_boost_123" if product_key == game_app.EXPLORE_BOOST_PRODUCT_KEY else "cs_test_other_123"
        return {
            "id": session_id,
            "url": f"https://checkout.stripe.test/session/{session_id}",
            "payment_intent": None,
            "amount_total": None,
            "currency": "jpy",
            "metadata": kwargs.get("metadata", {}),
        }


class _FakeStripeWebhookAPI:
    @staticmethod
    def construct_event(payload, sig_header, secret):
        if sig_header != "validsig" or secret != "whsec_test":
            raise _FakeStripeSignatureError("invalid signature")
        return json.loads(payload.decode("utf-8"))


class _FakeStripeModule:
    api_key = None
    error = SimpleNamespace(SignatureVerificationError=_FakeStripeSignatureError)
    checkout = SimpleNamespace(Session=_FakeStripeSessionAPI)
    Webhook = _FakeStripeWebhookAPI


class ShopExploreBoostPaymentsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        self.old_stripe = game_app.stripe
        self.old_secret_key = game_app.STRIPE_SECRET_KEY
        self.old_publishable_key = game_app.STRIPE_PUBLISHABLE_KEY
        self.old_webhook_secret = game_app.STRIPE_WEBHOOK_SECRET
        self.old_boost_price_id = game_app.STRIPE_PRICE_ID_EXPLORE_BOOST_14D
        self.old_public_game_url = game_app.PUBLIC_GAME_URL

        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True
        game_app.stripe = _FakeStripeModule
        game_app.STRIPE_SECRET_KEY = "sk_test_boost"
        game_app.STRIPE_PUBLISHABLE_KEY = "pk_test_boost"
        game_app.STRIPE_WEBHOOK_SECRET = "whsec_test"
        game_app.STRIPE_PRICE_ID_EXPLORE_BOOST_14D = "price_test_explore_boost"
        game_app.PUBLIC_GAME_URL = "https://robolabo.site"

        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected)
                VALUES (?, ?, ?, 1, 1)
                """,
                ("boost_admin", generate_password_hash("pw"), now),
            )
            db.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                ("boost_user", generate_password_hash("pw"), now - (100 * 3600)),
            )
            self.admin_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("boost_admin",)).fetchone()["id"])
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("boost_user",)).fetchone()["id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        game_app.stripe = self.old_stripe
        game_app.STRIPE_SECRET_KEY = self.old_secret_key
        game_app.STRIPE_PUBLISHABLE_KEY = self.old_publishable_key
        game_app.STRIPE_WEBHOOK_SECRET = self.old_webhook_secret
        game_app.STRIPE_PRICE_ID_EXPLORE_BOOST_14D = self.old_boost_price_id
        game_app.PUBLIC_GAME_URL = self.old_public_game_url
        self.tmpdir.cleanup()

    def _login(self, client, user_id, username):
        with client.session_transaction() as sess:
            sess["user_id"] = int(user_id)
            sess["username"] = username

    def _completed_event_payload(self):
        return {
            "id": "evt_test_boost_completed_123",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_boost_123",
                    "payment_intent": "pi_test_boost_123",
                    "amount_total": 500,
                    "currency": "jpy",
                    "metadata": {
                        "user_id": str(self.user_id),
                        "product_key": game_app.EXPLORE_BOOST_PRODUCT_KEY,
                        "grant_type": "explore_boost",
                        "boost_days": "14",
                    },
                }
            },
        }

    def test_shop_checkout_requires_login(self):
        client = game_app.app.test_client()
        resp = client.post("/shop/explore-boost/checkout", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers.get("Location", ""))

    def test_shop_checkout_creates_checkout_session_and_order(self):
        client = game_app.app.test_client()
        self._login(client, self.user_id, "boost_user")

        resp = client.post("/shop/explore-boost/checkout", follow_redirects=False)

        self.assertEqual(resp.status_code, 303)
        self.assertEqual(resp.headers.get("Location"), "https://checkout.stripe.test/session/cs_test_boost_123")
        self.assertEqual(_FakeStripeSessionAPI.last_kwargs["metadata"]["user_id"], str(self.user_id))
        self.assertEqual(_FakeStripeSessionAPI.last_kwargs["metadata"]["product_key"], game_app.EXPLORE_BOOST_PRODUCT_KEY)
        self.assertEqual(_FakeStripeSessionAPI.last_kwargs["metadata"]["boost_days"], "14")
        self.assertIn("session_id={CHECKOUT_SESSION_ID}", _FakeStripeSessionAPI.last_kwargs["success_url"])

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT * FROM payment_orders WHERE user_id = ?", (self.user_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["product_key"], game_app.EXPLORE_BOOST_PRODUCT_KEY)
            self.assertEqual(row["status"], game_app.PAYMENT_STATUS_CREATED)
            self.assertEqual(int(row["boost_days"] or 0), 14)

    def test_shop_webhook_invalid_signature_returns_400(self):
        client = game_app.app.test_client()
        resp = client.post("/stripe/webhook", data=b"{}", headers={"Stripe-Signature": "invalid"})
        self.assertEqual(resp.status_code, 400)

    def test_checkout_session_completed_grants_explore_boost(self):
        client = game_app.app.test_client()
        self._login(client, self.user_id, "boost_user")
        client.post("/shop/explore-boost/checkout", follow_redirects=False)

        now_before = int(time.time())
        resp = client.post(
            "/stripe/webhook",
            data=json.dumps(self._completed_event_payload()).encode("utf-8"),
            headers={"Stripe-Signature": "validsig", "Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            order = db.execute(
                "SELECT * FROM payment_orders WHERE stripe_checkout_session_id = ?",
                ("cs_test_boost_123",),
            ).fetchone()
            user = db.execute("SELECT explore_boost_until FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(order["status"], game_app.PAYMENT_STATUS_GRANTED)
            self.assertEqual(order["stripe_event_id"], "evt_test_boost_completed_123")
            self.assertEqual(order["stripe_payment_intent_id"], "pi_test_boost_123")
            self.assertEqual(order["amount_jpy"], 500)
            self.assertGreater(int(order["ends_at"] or 0), now_before)
            self.assertGreater(int(user["explore_boost_until"] or 0), now_before)
            completed_audit = db.execute(
                "SELECT 1 FROM world_events_log WHERE event_type = ? LIMIT 1",
                (game_app.AUDIT_EVENT_TYPES["PAYMENT_COMPLETED"],),
            ).fetchone()
            grant_audit = db.execute(
                "SELECT 1 FROM world_events_log WHERE event_type = ? LIMIT 1",
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_BOOST_GRANT_SUCCESS"],),
            ).fetchone()
            self.assertIsNotNone(completed_audit)
            self.assertIsNotNone(grant_audit)

    def test_duplicate_webhook_event_does_not_double_grant(self):
        client = game_app.app.test_client()
        self._login(client, self.user_id, "boost_user")
        client.post("/shop/explore-boost/checkout", follow_redirects=False)
        payload = json.dumps(self._completed_event_payload()).encode("utf-8")

        first = client.post(
            "/stripe/webhook",
            data=payload,
            headers={"Stripe-Signature": "validsig", "Content-Type": "application/json"},
        )
        with game_app.app.app_context():
            db = game_app.get_db()
            first_until = int(
                db.execute("SELECT explore_boost_until FROM users WHERE id = ?", (self.user_id,)).fetchone()["explore_boost_until"]
                or 0
            )

        second = client.post(
            "/stripe/webhook",
            data=payload,
            headers={"Stripe-Signature": "validsig", "Content-Type": "application/json"},
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            second_until = int(
                db.execute("SELECT explore_boost_until FROM users WHERE id = ?", (self.user_id,)).fetchone()["explore_boost_until"]
                or 0
            )
            self.assertEqual(first_until, second_until)
            duplicate_audit = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ?",
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_BOOST_GRANT_SKIP_DUPLICATE"],),
            ).fetchone()["c"]
            self.assertGreaterEqual(int(duplicate_audit), 1)

    def test_paid_explore_boost_ct_is_20_seconds(self):
        now = int(time.time())
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET created_at = ?, explore_boost_until = ? WHERE id = ?", (now - (100 * 3600), now + 86400, self.user_id))
            db.commit()
            user = db.execute("SELECT is_admin, created_at, explore_boost_until FROM users WHERE id = ?", (self.user_id,)).fetchone()
        self.assertEqual(game_app._explore_ct_seconds_for_user(user, now_ts=now), 20)

    def test_paid_explore_boost_expired_returns_to_40_seconds(self):
        now = int(time.time())
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET created_at = ?, explore_boost_until = ? WHERE id = ?", (now - (100 * 3600), now - 60, self.user_id))
            db.commit()
            user = db.execute("SELECT is_admin, created_at, explore_boost_until FROM users WHERE id = ?", (self.user_id,)).fetchone()
        self.assertEqual(game_app._explore_ct_seconds_for_user(user, now_ts=now), 40)

    def test_admin_payments_lists_explore_boost_order(self):
        client = game_app.app.test_client()
        self._login(client, self.admin_id, "boost_admin")
        now = int(time.time())
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                INSERT INTO payment_orders (
                    user_id, product_key, stripe_checkout_session_id, stripe_payment_intent_id,
                    stripe_event_id, amount_jpy, currency, status, grant_type,
                    boost_days, starts_at, ends_at, granted_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.user_id,
                    game_app.EXPLORE_BOOST_PRODUCT_KEY,
                    "cs_test_boost_admin_view",
                    "pi_test_boost_admin_view",
                    "evt_test_boost_admin_view",
                    300,
                    "jpy",
                    game_app.PAYMENT_STATUS_GRANTED,
                    "explore_boost",
                    14,
                    now,
                    now + (14 * 86400),
                    now,
                    now,
                    now,
                ),
            )
            db.commit()
        resp = client.get("/admin/payments?product_key=explore_boost_14d")
        html = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("支払い履歴", html)
        self.assertIn("explore_boost_14d", html)
        self.assertIn("boost_user", html)


if __name__ == "__main__":
    unittest.main()

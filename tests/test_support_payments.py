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
        suffix = {
            game_app.SUPPORT_PACK_PRODUCT_KEY: "founder",
            game_app.SUPPORT_PACK_LAB_PRODUCT_KEY: "lab",
        }.get(product_key, "other")
        session_id = f"cs_test_support_{suffix}_123"
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


class SupportPaymentsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        self.old_stripe = game_app.stripe
        self.old_secret_key = game_app.STRIPE_SECRET_KEY
        self.old_publishable_key = game_app.STRIPE_PUBLISHABLE_KEY
        self.old_webhook_secret = game_app.STRIPE_WEBHOOK_SECRET
        self.old_founder_price_id = game_app.STRIPE_PRICE_ID_SUPPORT_FOUNDER
        self.old_lab_price_id = game_app.STRIPE_PRICE_ID_SUPPORT_LAB
        self.old_public_game_url = game_app.PUBLIC_GAME_URL

        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True
        game_app.stripe = _FakeStripeModule
        game_app.STRIPE_SECRET_KEY = "sk_test_support"
        game_app.STRIPE_PUBLISHABLE_KEY = "pk_test_support"
        game_app.STRIPE_WEBHOOK_SECRET = "whsec_test"
        game_app.STRIPE_PRICE_ID_SUPPORT_FOUNDER = "price_support_founder"
        game_app.STRIPE_PRICE_ID_SUPPORT_LAB = "price_support_lab"
        game_app.PUBLIC_GAME_URL = "https://robolabo.site"

        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected)
                VALUES (?, ?, ?, 1, 1)
                """,
                ("payments_admin", generate_password_hash("pw"), now),
            )
            db.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                ("support_user", generate_password_hash("pw"), now),
            )
            self.admin_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("payments_admin",)).fetchone()["id"])
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("support_user",)).fetchone()["id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        game_app.stripe = self.old_stripe
        game_app.STRIPE_SECRET_KEY = self.old_secret_key
        game_app.STRIPE_PUBLISHABLE_KEY = self.old_publishable_key
        game_app.STRIPE_WEBHOOK_SECRET = self.old_webhook_secret
        game_app.STRIPE_PRICE_ID_SUPPORT_FOUNDER = self.old_founder_price_id
        game_app.STRIPE_PRICE_ID_SUPPORT_LAB = self.old_lab_price_id
        game_app.PUBLIC_GAME_URL = self.old_public_game_url
        self.tmpdir.cleanup()

    def _login(self, client, user_id, username):
        with client.session_transaction() as sess:
            sess["user_id"] = int(user_id)
            sess["username"] = username

    def _completed_event_payload(self, *, product_key, session_id, payment_intent, event_id, amount_jpy):
        return {
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": session_id,
                    "payment_intent": payment_intent,
                    "amount_total": amount_jpy,
                    "currency": "jpy",
                    "metadata": {
                        "user_id": str(self.user_id),
                        "product_key": product_key,
                        "grant_type": "decor",
                    },
                }
            },
        }

    def test_support_checkout_requires_login(self):
        client = game_app.app.test_client()
        resp = client.post("/support/founder/checkout", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers.get("Location", ""))

    def test_support_page_shows_two_support_products(self):
        client = game_app.app.test_client()
        self._login(client, self.user_id, "support_user")
        resp = client.get("/support")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("ロボらぼの開発を応援できます", html)
        self.assertIn("戦力差はつきません", html)
        self.assertIn("創設支援パック", html)
        self.assertIn("ラボ維持支援パック", html)
        self.assertIn("支援する（100円）", html)
        self.assertIn("しっかり支援する（300円）", html)

    def test_founder_checkout_creates_checkout_session_and_order(self):
        client = game_app.app.test_client()
        self._login(client, self.user_id, "support_user")

        resp = client.post("/support/founder/checkout", follow_redirects=False)

        self.assertEqual(resp.status_code, 303)
        self.assertEqual(resp.headers.get("Location"), "https://checkout.stripe.test/session/cs_test_support_founder_123")
        self.assertEqual(_FakeStripeSessionAPI.last_kwargs["metadata"]["user_id"], str(self.user_id))
        self.assertEqual(_FakeStripeSessionAPI.last_kwargs["metadata"]["product_key"], game_app.SUPPORT_PACK_PRODUCT_KEY)
        self.assertIn("session_id={CHECKOUT_SESSION_ID}", _FakeStripeSessionAPI.last_kwargs["success_url"])

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT * FROM payment_orders WHERE user_id = ?", (self.user_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["product_key"], game_app.SUPPORT_PACK_PRODUCT_KEY)
            self.assertEqual(row["stripe_checkout_session_id"], "cs_test_support_founder_123")
            self.assertEqual(row["status"], game_app.PAYMENT_STATUS_CREATED)

    def test_lab_checkout_creates_checkout_session_and_order(self):
        client = game_app.app.test_client()
        self._login(client, self.user_id, "support_user")

        resp = client.post("/support/lab/checkout", follow_redirects=False)

        self.assertEqual(resp.status_code, 303)
        self.assertEqual(resp.headers.get("Location"), "https://checkout.stripe.test/session/cs_test_support_lab_123")
        self.assertEqual(_FakeStripeSessionAPI.last_kwargs["metadata"]["product_key"], game_app.SUPPORT_PACK_LAB_PRODUCT_KEY)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT * FROM payment_orders WHERE user_id = ?", (self.user_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["product_key"], game_app.SUPPORT_PACK_LAB_PRODUCT_KEY)
            self.assertEqual(row["status"], game_app.PAYMENT_STATUS_CREATED)

    def test_stripe_webhook_invalid_signature_returns_400(self):
        client = game_app.app.test_client()
        resp = client.post("/stripe/webhook", data=b"{}", headers={"Stripe-Signature": "invalid"})
        self.assertEqual(resp.status_code, 400)

    def test_checkout_session_completed_grants_founder_support_rewards(self):
        client = game_app.app.test_client()
        self._login(client, self.user_id, "support_user")
        client.post("/support/founder/checkout", follow_redirects=False)

        resp = client.post(
            "/stripe/webhook",
            data=json.dumps(
                self._completed_event_payload(
                    product_key=game_app.SUPPORT_PACK_PRODUCT_KEY,
                    session_id="cs_test_support_founder_123",
                    payment_intent="pi_test_support_founder_123",
                    event_id="evt_test_completed_founder_123",
                    amount_jpy=100,
                )
            ).encode("utf-8"),
            headers={"Stripe-Signature": "validsig", "Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            order = db.execute(
                "SELECT * FROM payment_orders WHERE stripe_checkout_session_id = ?",
                ("cs_test_support_founder_123",),
            ).fetchone()
            self.assertEqual(order["status"], game_app.PAYMENT_STATUS_GRANTED)
            decor = db.execute(
                """
                SELECT 1
                FROM user_decor_inventory udi
                JOIN robot_decor_assets rda ON rda.id = udi.decor_asset_id
                WHERE udi.user_id = ? AND rda.key = ?
                """,
                (self.user_id, game_app.SUPPORT_PACK_DECOR_KEY),
            ).fetchone()
            trophy = db.execute(
                """
                SELECT 1
                FROM user_trophies
                WHERE user_id = ? AND trophy_key = ?
                """,
                (self.user_id, game_app.SUPPORTER_FOUNDER_TROPHY_KEY),
            ).fetchone()
            self.assertIsNotNone(decor)
            self.assertIsNotNone(trophy)

    def test_checkout_session_completed_grants_lab_support_rewards(self):
        client = game_app.app.test_client()
        self._login(client, self.user_id, "support_user")
        client.post("/support/lab/checkout", follow_redirects=False)

        resp = client.post(
            "/stripe/webhook",
            data=json.dumps(
                self._completed_event_payload(
                    product_key=game_app.SUPPORT_PACK_LAB_PRODUCT_KEY,
                    session_id="cs_test_support_lab_123",
                    payment_intent="pi_test_support_lab_123",
                    event_id="evt_test_completed_lab_123",
                    amount_jpy=300,
                )
            ).encode("utf-8"),
            headers={"Stripe-Signature": "validsig", "Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            order = db.execute(
                "SELECT * FROM payment_orders WHERE stripe_checkout_session_id = ?",
                ("cs_test_support_lab_123",),
            ).fetchone()
            self.assertEqual(order["status"], game_app.PAYMENT_STATUS_GRANTED)
            decor = db.execute(
                """
                SELECT 1
                FROM user_decor_inventory udi
                JOIN robot_decor_assets rda ON rda.id = udi.decor_asset_id
                WHERE udi.user_id = ? AND rda.key = ?
                """,
                (self.user_id, game_app.SUPPORT_PACK_LAB_DECOR_KEY),
            ).fetchone()
            trophy = db.execute(
                """
                SELECT 1
                FROM user_trophies
                WHERE user_id = ? AND trophy_key = ?
                """,
                (self.user_id, game_app.SUPPORTER_LAB_TROPHY_KEY),
            ).fetchone()
            self.assertIsNotNone(decor)
            self.assertIsNotNone(trophy)

    def test_duplicate_webhook_event_does_not_double_grant(self):
        client = game_app.app.test_client()
        self._login(client, self.user_id, "support_user")
        client.post("/support/founder/checkout", follow_redirects=False)
        payload = json.dumps(
            self._completed_event_payload(
                product_key=game_app.SUPPORT_PACK_PRODUCT_KEY,
                session_id="cs_test_support_founder_123",
                payment_intent="pi_test_support_founder_123",
                event_id="evt_test_completed_founder_123",
                amount_jpy=100,
            )
        ).encode("utf-8")

        first = client.post(
            "/stripe/webhook",
            data=payload,
            headers={"Stripe-Signature": "validsig", "Content-Type": "application/json"},
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
            count = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM user_decor_inventory udi
                JOIN robot_decor_assets rda ON rda.id = udi.decor_asset_id
                WHERE udi.user_id = ? AND rda.key = ?
                """,
                (self.user_id, game_app.SUPPORT_PACK_DECOR_KEY),
            ).fetchone()["c"]
            trophy_count = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM user_trophies
                WHERE user_id = ? AND trophy_key = ?
                """,
                (self.user_id, game_app.SUPPORTER_FOUNDER_TROPHY_KEY),
            ).fetchone()["c"]
            self.assertEqual(count, 1)
            self.assertEqual(trophy_count, 1)

    def test_admin_payments_page_lists_payment_history(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO payment_orders (
                    user_id,
                    product_key,
                    stripe_checkout_session_id,
                    stripe_payment_intent_id,
                    stripe_event_id,
                    amount_jpy,
                    currency,
                    status,
                    grant_type,
                    granted_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.user_id,
                    game_app.SUPPORT_PACK_PRODUCT_KEY,
                    "cs_admin_view_001",
                    "pi_admin_view_001",
                    "evt_admin_view_001",
                    100,
                    "jpy",
                    game_app.PAYMENT_STATUS_GRANTED,
                    "decor",
                    now,
                    now,
                    now,
                ),
            )
            db.commit()

        client = game_app.app.test_client()
        self._login(client, self.admin_id, "payments_admin")
        resp = client.get("/admin/payments?username=support_user")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("支払い履歴", html)
        self.assertIn("support_user", html)
        self.assertIn("cs_admin_view_001", html)
        self.assertIn(game_app.SUPPORT_PACK_PRODUCT_KEY, html)


if __name__ == "__main__":
    unittest.main()

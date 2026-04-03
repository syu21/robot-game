from pathlib import Path
import unittest


class PaymentDocsTests(unittest.TestCase):
    def test_payment_spec_exists_and_lists_routes_and_audit_events(self):
        text = Path("docs/PAYMENT_SPEC.md").read_text(encoding="utf-8")
        self.assertIn("support_pack_founder", text)
        self.assertIn("support_pack_lab", text)
        self.assertIn("explore_boost_14d", text)
        self.assertIn("/shop", text)
        self.assertIn("/shop/explore-boost/checkout", text)
        self.assertIn("/support", text)
        self.assertIn("/support/founder/checkout", text)
        self.assertIn("/support/lab/checkout", text)
        self.assertIn("/payment/success", text)
        self.assertIn("/payment/cancel", text)
        self.assertIn("/stripe/webhook", text)
        self.assertIn("checkout.session.completed", text)
        self.assertIn("STRIPE_PRICE_ID_SUPPORT_FOUNDER", text)
        self.assertIn("STRIPE_PRICE_ID_SUPPORT_LAB", text)
        self.assertIn("STRIPE_PRICE_ID_EXPLORE_BOOST_14D", text)
        self.assertIn("user_trophies", text)
        self.assertIn("supporter_founder", text)
        self.assertIn("supporter_lab", text)
        self.assertIn("founder_badge_silver", text)
        self.assertIn("lab_badge_gold", text)
        self.assertIn("100円", text)
        self.assertIn("300円", text)
        self.assertIn("500円", text)
        self.assertIn("audit.payment.checkout.create", text)
        self.assertIn("audit.trophy.grant.success", text)
        self.assertIn("audit.explore_boost.grant.success", text)
        self.assertIn("stripe listen --forward-to http://127.0.0.1:5050/stripe/webhook", text)

    def test_docs_readme_mentions_payment_spec(self):
        text = Path("docs/README.md").read_text(encoding="utf-8")
        self.assertIn("docs/PAYMENT_SPEC.md", text)


if __name__ == "__main__":
    unittest.main()

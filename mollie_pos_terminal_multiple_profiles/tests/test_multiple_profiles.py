from unittest.mock import patch

import requests

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.mollie_pos_terminal_multiple_profiles.hooks import post_init_hook
from odoo.addons.point_of_sale.tests.common import TestPoSCommon

REQUESTS_PATH = (
    "odoo.addons.mollie_pos_terminal_multiple_profiles.models"
    ".mollie_pos_terminal.requests"
)
SYNC_PATH = (
    "odoo.addons.mollie_pos_terminal.models.mollie_pos_terminal"
    ".MolliePosTerminal._sync_mollie_terminals"
)


class _FakeResponse:
    def __init__(self, json_data, status_code=200, raise_http=False):
        self._json = json_data
        self.status_code = status_code
        self._raise_http = raise_http

    def json(self):
        return self._json

    def raise_for_status(self):
        if self._raise_http:
            raise requests.exceptions.HTTPError()
        return None


def _terminal_payload(terminals):
    return _FakeResponse(
        {"count": len(terminals), "_embedded": {"terminals": terminals}}
    )


def _mollie_auth_error():
    return _FakeResponse(
        {
            "detail": "Invalid Authorization header",
            "status": 400,
            "title": "Bad Request",
        },
        status_code=400,
        raise_http=True,
    )


def _terminal(terminal_id, currency, **extra):
    return {
        "id": terminal_id,
        "description": f"Terminal {terminal_id}",
        "profileId": f"pfl_{terminal_id}",
        "serialNumber": f"SN-{terminal_id}",
        "status": "active",
        "currency": currency,
        **extra,
    }


@tagged("post_install", "-at_install")
class TestMollieMultipleProfiles(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.config_a = cls.basic_config
        cls.config_b = cls.other_currency_config
        cls.config_a.mollie_terminal_api_key = "key_A"
        cls.config_b.mollie_terminal_api_key = "key_B"

        cls.terminal = cls.env["mollie.pos.terminal"].create(
            {
                "name": "Terminal A",
                "terminal_id": "term_A",
                "status": "active",
                "company_id": cls.env.company.id,
            }
        )
        cls.payment_method = cls.env["pos.payment.method"].create(
            {
                "name": "Mollie",
                "use_payment_terminal": "mollie",
                "mollie_pos_terminal_id": cls.terminal.id,
                "company_id": cls.env.company.id,
            }
        )

        cls.config_a.write({"payment_method_ids": [(4, cls.payment_method.id)]})

        cls.session_a = cls._make_session(cls.config_a)
        cls.session_b = cls._make_session(cls.config_b)

    @classmethod
    def _make_session(cls, config):
        return cls.env["pos.session"].create(
            {"config_id": config.id, "user_id": cls.env.uid}
        )

    def _payment_data(self, session, amount=10.0, **extra):
        data = {
            "session_id": session.id,
            "amount": amount,
            "curruncy": "EUR",
            "description": "Order 0001",
            "mollie_uid": "uid-1",
            "order_id": "order-uuid",
            "payment_method_id": self.payment_method.id,
            "order_type": "pos",
        }
        data.update(extra)
        return data

    def _make_payment_record(self, session, name="tr_open", status="open"):
        return self.env["mollie.pos.terminal.payments"].create(
            {
                "name": name,
                "mollie_uid": "uid-1",
                "terminal_id": self.terminal.id,
                "session_id": session.id,
                "status": status,
            }
        )

    @staticmethod
    def _auth_header(mock_request):
        return mock_request.call_args.kwargs["headers"]["Authorization"]

    def test_api_call_context_key(self):
        with patch(REQUESTS_PATH) as mock_requests:
            mock_requests.request.return_value = _FakeResponse({"count": 0})
            self.terminal.with_context(mollie_api_key="key_A")._mollie_api_call(
                "/terminals", method="GET"
            )
        self.assertEqual(self._auth_header(mock_requests.request), "Bearer key_A")

    def test_api_call_missing_key(self):
        with patch(REQUESTS_PATH) as mock_requests:
            with self.assertRaises(ValidationError):
                self.terminal._mollie_api_call("/terminals", method="GET")
            mock_requests.request.assert_not_called()

    def test_payment_request(self):
        with patch(REQUESTS_PATH) as mock_requests:
            mock_requests.request.return_value = _FakeResponse(
                {"id": "tr_new", "status": "open"}
            )
            self.payment_method.mollie_payment_request(
                self._payment_data(self.session_a)
            )

        method, url = mock_requests.request.call_args.args
        self.assertEqual(method, "POST")
        self.assertIn("/v2/payments", url)
        self.assertEqual(self._auth_header(mock_requests.request), "Bearer key_A")

        created = self.env["mollie.pos.terminal.payments"].search(
            [("name", "=", "tr_new")]
        )
        self.assertEqual(len(created), 1)
        self.assertEqual(created.session_id, self.session_a)
        self.assertEqual(created.terminal_id, self.terminal)

    def test_payment_request_other_pos(self):
        with patch(REQUESTS_PATH) as mock_requests:
            mock_requests.request.return_value = _FakeResponse(
                {"id": "tr_new_b", "status": "open"}
            )
            self.payment_method.mollie_payment_request(
                self._payment_data(self.session_b)
            )
        self.assertEqual(self._auth_header(mock_requests.request), "Bearer key_B")

    def test_payment_request_missing_key(self):
        config_c = self.env["pos.config"].create({"name": "PoS No Key"})
        session_c = self._make_session(config_c)
        with patch(REQUESTS_PATH) as mock_requests:
            with self.assertRaises(ValidationError):
                self.payment_method.mollie_payment_request(
                    self._payment_data(session_c)
                )
            mock_requests.request.assert_not_called()

    def test_refund_request(self):
        with patch(REQUESTS_PATH) as mock_requests:
            mock_requests.request.return_value = _FakeResponse(
                {"id": "rf_new", "status": "pending"}
            )
            self.payment_method.mollie_payment_request(
                self._payment_data(
                    self.session_a,
                    amount=-5.0,
                    mollie_origin_transaction_id="tr_origin",
                )
            )
        method, url = mock_requests.request.call_args.args
        self.assertEqual(method, "POST")
        self.assertIn("/v2/payments/tr_origin/refunds", url)
        self.assertEqual(self._auth_header(mock_requests.request), "Bearer key_A")

    def test_cancel_payment(self):
        self._make_payment_record(self.session_a, name="tr_open", status="open")
        with patch(REQUESTS_PATH) as mock_requests:
            mock_requests.request.return_value = _FakeResponse(True, status_code=204)
            self.env["mollie.pos.terminal.payments"].mollie_cancel_payment_request(
                transaction_id="tr_open"
            )
        method, url = mock_requests.request.call_args.args
        self.assertEqual(method, "DELETE")
        self.assertIn("/v2/payments/tr_open", url)
        self.assertEqual(self._auth_header(mock_requests.request), "Bearer key_A")

    def test_cancel_payment_missing_key(self):
        config_c = self.env["pos.config"].create({"name": "PoS No Key"})
        session_c = self._make_session(config_c)
        self._make_payment_record(session_c, name="tr_nokey", status="open")
        with patch(REQUESTS_PATH):
            with self.assertRaises(ValidationError):
                self.env["mollie.pos.terminal.payments"].mollie_cancel_payment_request(
                    transaction_id="tr_nokey"
                )

    def test_process_webhook(self):
        payment = self._make_payment_record(
            self.session_a, name="tr_open", status="open"
        )
        with patch(REQUESTS_PATH) as mock_requests:
            mock_requests.request.return_value = _FakeResponse(
                {"id": "tr_open", "status": "paid"}
            )
            payment._mollie_process_webhook({"id": "tr_open"}, notify=False)

        method, url = mock_requests.request.call_args.args
        self.assertEqual(method, "GET")
        self.assertEqual(self._auth_header(mock_requests.request), "Bearer key_A")
        self.assertEqual(payment.status, "paid")

    def test_payment_details(self):
        order = self.env["pos.order"].create(
            {
                "session_id": self.session_a.id,
                "company_id": self.env.company.id,
                "amount_tax": 0.0,
                "amount_total": 10.0,
                "amount_paid": 10.0,
                "amount_return": 0.0,
            }
        )
        self.env["pos.payment"].create(
            {
                "pos_order_id": order.id,
                "amount": 10.0,
                "payment_method_id": self.payment_method.id,
                "transaction_id": "tr_open",
            }
        )
        with patch(REQUESTS_PATH) as mock_requests:
            mock_requests.request.return_value = _FakeResponse(
                {
                    "status": "paid",
                    "amountRefunded": {"value": "2.50"},
                    "amountRemaining": {"value": "7.50"},
                }
            )
            result = order.get_mollie_payment_details(self.session_a.id)

        self.assertEqual(self._auth_header(mock_requests.request), "Bearer key_A")
        self.assertEqual(result["amount_refunded"], 2.5)
        self.assertEqual(result["amount_remaining"], 7.5)

    def test_post_init_migration(self):
        self.env.company.sudo().mollie_terminal_api_key = "migrated_key"
        self.config_a.mollie_terminal_api_key = False

        post_init_hook(self.env(su=True))

        self.assertEqual(self.config_a.mollie_terminal_api_key, "migrated_key")

    def test_terminal_sync(self):
        seen = []

        def _fake_sync(self):
            seen.append(self.env.context.get("mollie_api_key"))

        wizard = self.env["sync.mollie.terminal"].create({})
        with patch(SYNC_PATH, autospec=True, side_effect=_fake_sync):
            wizard.sync_now()
        self.assertEqual(set(seen), {"key_A", "key_B"})

    def test_terminal_sync_shared_key(self):
        self.config_b.mollie_terminal_api_key = "key_A"
        seen = []

        def _fake_sync(self):
            seen.append(self.env.context.get("mollie_api_key"))

        wizard = self.env["sync.mollie.terminal"].create({})
        with patch(SYNC_PATH, autospec=True, side_effect=_fake_sync):
            wizard.sync_now()
        self.assertEqual(seen, ["key_A"])

    def test_terminal_sync_no_keys(self):
        (self.config_a | self.config_b).mollie_terminal_api_key = False
        wizard = self.env["sync.mollie.terminal"].create({})
        with self.assertRaises(ValidationError):
            wizard.sync_now()

    def test_terminal_sync_multiple_keys(self):
        currency = self.env.company.currency_id.name

        def _fake_request(method, url, **kwargs):
            key = kwargs["headers"]["Authorization"]
            return _terminal_payload(
                {
                    "Bearer key_A": [_terminal("term_A1", currency)],
                    "Bearer key_B": [_terminal("term_B1", currency)],
                }.get(key, [])
            )

        wizard = self.env["sync.mollie.terminal"].create({})
        with patch(REQUESTS_PATH) as mock_requests:
            mock_requests.request.side_effect = _fake_request
            result = wizard.sync_now()

        self.assertEqual(mock_requests.request.call_count, 2)
        self.assertFalse(result)
        Terminal = self.env["mollie.pos.terminal"]
        self.assertTrue(Terminal.search([("terminal_id", "=", "term_A1")]))
        self.assertTrue(Terminal.search([("terminal_id", "=", "term_B1")]))

    def test_terminal_sync_invalid_key(self):
        currency = self.env.company.currency_id.name

        def _fake_request(method, url, **kwargs):
            if kwargs["headers"]["Authorization"] == "Bearer key_A":
                return _terminal_payload([_terminal("term_A1", currency)])
            return _mollie_auth_error()

        wizard = self.env["sync.mollie.terminal"].create({})
        with patch(REQUESTS_PATH) as mock_requests:
            mock_requests.exceptions = requests.exceptions
            mock_requests.request.side_effect = _fake_request
            result = wizard.sync_now()

        Terminal = self.env["mollie.pos.terminal"]
        self.assertTrue(Terminal.search([("terminal_id", "=", "term_A1")]))
        self.assertEqual(result["tag"], "display_notification")
        self.assertEqual(result["params"]["type"], "warning")
        self.assertIn(self.config_b.name, result["params"]["message"])

    def test_terminal_sync_all_invalid(self):
        wizard = self.env["sync.mollie.terminal"].create({})
        with patch(REQUESTS_PATH) as mock_requests:
            mock_requests.exceptions = requests.exceptions
            mock_requests.request.side_effect = lambda *a, **k: _mollie_auth_error()
            with self.assertRaises(ValidationError):
                wizard.sync_now()
        self.assertFalse(
            self.env["mollie.pos.terminal"].search(
                [
                    ("terminal_id", "in", ["term_A1", "term_B1"]),
                ]
            )
        )

    def test_terminal_sync_currency_error(self):
        currency = self.env.company.currency_id.name

        def _fake_request(method, url, **kwargs):
            if kwargs["headers"]["Authorization"] == "Bearer key_A":
                return _terminal_payload(
                    [
                        _terminal("term_A1", currency),
                        _terminal("term_A2", "ZZZ"),
                    ]
                )
            return _terminal_payload([_terminal("term_B1", currency)])

        wizard = self.env["sync.mollie.terminal"].create({})
        with patch(REQUESTS_PATH) as mock_requests:
            mock_requests.request.side_effect = _fake_request
            result = wizard.sync_now()

        Terminal = self.env["mollie.pos.terminal"]
        self.assertFalse(Terminal.search([("terminal_id", "=", "term_A1")]))
        self.assertFalse(Terminal.search([("terminal_id", "=", "term_A2")]))
        self.assertTrue(Terminal.search([("terminal_id", "=", "term_B1")]))
        self.assertEqual(result["tag"], "display_notification")

from odoo import models
from odoo.exceptions import ValidationError


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    def _mollie_get_pos_config_from_session(self, session_id):
        session = self.env["pos.session"].sudo().browse(session_id)
        return session.config_id if session.exists() else False

    def _mollie_with_pos_context(self, pos_config):
        api_key = pos_config.mollie_terminal_api_key if pos_config else False
        if not api_key:
            raise ValidationError(
                self.env._("Set a Mollie Terminal API key on this POS.")
            )
        return {"mollie_api_key": api_key, "pos_config_id": pos_config.id}

    def mollie_payment_request(self, data):
        # avoid handling old responses multiple times
        self.sudo().mollie_latest_response = {}
        pos_config = self._mollie_get_pos_config_from_session(data.get("session_id"))
        ctx = self._mollie_with_pos_context(pos_config)
        terminal = self.mollie_pos_terminal_id.with_context(**ctx)
        if data.get("amount") >= 0:
            return terminal._api_make_payment_request(data)
        elif data.get("mollie_origin_transaction_id"):
            return terminal._api_make_refund_request(data)
        return False

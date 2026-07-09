from odoo import models
from odoo.exceptions import ValidationError


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _mollie_get_pos_config_from_session(self, pos_session_id):
        session = self.env["pos.session"].sudo().browse(pos_session_id)
        return session.config_id if session.exists() else False

    def get_mollie_payment_details(self, pos_session_id):
        mollie_line = self.payment_ids.filtered(
            lambda line: line.transaction_id
            and line.payment_method_id.use_payment_terminal == "mollie"
        )
        if len(mollie_line) == 1:
            pos_config = self._mollie_get_pos_config_from_session(pos_session_id)
            api_key = pos_config.mollie_terminal_api_key if pos_config else False
            if not api_key:
                raise ValidationError(
                    self.env._("Set a Mollie Terminal API key on this POS.")
                )
            terminal = (
                mollie_line.payment_method_id.mollie_pos_terminal_id.with_context(
                    mollie_api_key=api_key,
                    pos_config_id=pos_config.id,
                )
            )
            mollie_payment_data = terminal._api_get_mollie_payment_status(
                mollie_line.transaction_id
            )
            if mollie_payment_data:
                return {
                    "amount_refunded": float(
                        mollie_payment_data.get("amountRefunded", {}).get("value", "0")
                    ),
                    "amount_remaining": float(
                        mollie_payment_data.get("amountRemaining", {}).get("value", "0")
                    ),
                }
        return False

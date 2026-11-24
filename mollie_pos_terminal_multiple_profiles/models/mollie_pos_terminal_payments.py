from odoo import api, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain


class MolliePosTerminalPayments(models.Model):
    _inherit = "mollie.pos.terminal.payments"

    def _mollie_get_pos_context_from_payment(self, mollie_payment):
        pos_config = (
            mollie_payment.session_id.config_id if mollie_payment.session_id else False
        )
        api_key = pos_config.mollie_terminal_api_key if pos_config else False
        if not api_key:
            raise ValidationError(
                self.env._("Set a Mollie Terminal API key on this POS.")
            )
        return {"mollie_api_key": api_key, "pos_config_id": pos_config.id}

    @api.model
    def mollie_cancel_payment_request(self, transaction_id=None, mollie_uid=None):
        if transaction_id:
            domain = Domain("name", "=", transaction_id)
        elif mollie_uid:
            domain = Domain("mollie_uid", "=", mollie_uid)
        else:
            return {}
        mollie_payment = self.search(domain, limit=1)
        if mollie_payment and mollie_payment.status == "open":
            ctx = self._mollie_get_pos_context_from_payment(mollie_payment)
            return mollie_payment.terminal_id.with_context(
                **ctx
            )._api_cancel_mollie_payment(mollie_payment.name)
        return {}

    def _mollie_process_webhook(self, webhook_data, order_type="pos", notify=True):
        mollie_payment = self.sudo().search(
            Domain("name", "=", webhook_data.get("id")), limit=1
        )
        if mollie_payment:
            ctx = self._mollie_get_pos_context_from_payment(mollie_payment)
            payment_status = mollie_payment.terminal_id.with_context(
                **ctx
            )._api_get_mollie_payment_status(webhook_data.get("id"))
            if payment_status and payment_status.get("status"):
                mollie_payment.write(
                    {
                        "mollie_latest_response": payment_status,
                        "status": payment_status.get("status"),
                    }
                )

                if notify:
                    mollie_payment.session_id.config_id._notify(
                        "MOLLIE_TERMINAL_RESPONSE",
                        mollie_payment.session_id.config_id.id,
                    )

                for refund_data in payment_status.get("_embedded", {}).get(
                    "refunds", []
                ):
                    refund_payment = self.sudo().search(
                        Domain("name", "=", refund_data.get("id")), limit=1
                    )
                    refund_payment.write(
                        {
                            "mollie_latest_response": refund_data,
                            "status": refund_data.get("status"),
                        }
                    )

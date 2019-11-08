# -*- coding: utf-8 -*-
from mollie.api.client import Client
from odoo import models, fields

import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    _mollie_client = Client()

    is_mollie_refund = fields.Boolean("Is Mollie Refund")
    is_moliie_payment = fields.Boolean(compute="_compute_is_mollie")

    # check the reversed invoice is payment done by mollie
    def _compute_is_mollie(self):
        for move in self:
            move.is_moliie_payment = (
                "mollie"
                in move.reversed_entry_id.transaction_ids.acquirer_id.mapped(
                    "provider"
                )
            )

    # create mollie refund order payment
    def mollie_refund_orders_create(self):
        self.ensure_one()
        provider = (
            self.env["payment.acquirer"].sudo()._get_main_mollie_provider()
        )
        key = provider._get_mollie_api_keys(provider.state)["mollie_api_key"]
        self._mollie_client.set_api_key(key)

        reference = self.reversed_entry_id.transaction_ids.mapped(
            "acquirer_reference"
        )
        if isinstance(reference and reference[0], bool):
            return

        try:
            payment = self._mollie_client.payments.get(reference[0])
            self._mollie_client.payment_refunds.on(payment).create(
                {
                    "amount": {
                        "value": "%.2f" % self.amount_total,
                        "currency": self.currency_id.name,
                    }
                }
            )
            self.is_mollie_refund = True
        except Exception as e:
            _logger.warning(e)

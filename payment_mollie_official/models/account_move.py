# -*- coding: utf-8 -*-
from mollie.api.client import Client
from odoo import models, fields

import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    _mollie_client = Client()

    is_mollie_refund = fields.Boolean(compute="_compute_is_mollie_refund")

    # check the reversed invoice is payment done by mollie
    def _compute_is_mollie_refund(self):
        for move in self:
            if (
                move.type != "out_refund"
                or move.state != "posted"
                or move.invoice_payment_state == "paid"
            ):
                move.is_mollie_refund = False
                continue

            provider = (
                self.env["payment.acquirer"].sudo()._get_main_mollie_provider()
            )
            key = provider._get_mollie_api_keys(provider.state)[
                "mollie_api_key"
            ]
            self._mollie_client.set_api_key(key)

            if not move.reversed_entry_id.transaction_ids:
                transaction_ids = (
                    self.env["payment.transaction"]
                    .sudo()
                    .search([("invoice_ids", "in", move.reversed_entry_id.id)])
                )
            else:
                transaction_ids = move.reversed_entry_id.transaction_ids

            reference = transaction_ids.filtered(
                lambda t: t.acquirer_id.provider == "mollie"
            ).mapped("acquirer_reference")

            if isinstance(reference and reference[0], bool) or reference == []:
                move.is_mollie_refund = False
                continue

            payment = self._mollie_client.payments.get(reference[0])
            if payment.get("_links").get("refunds"):
                move.is_mollie_refund = False
                continue

            move.is_mollie_refund = "mollie" in transaction_ids[
                0
            ].acquirer_id.mapped("provider")

    # create mollie refund order payment
    def mollie_refund_orders_create(self):
        self.ensure_one()
        provider = (
            self.env["payment.acquirer"].sudo()._get_main_mollie_provider()
        )
        key = provider._get_mollie_api_keys(provider.state)["mollie_api_key"]
        self._mollie_client.set_api_key(key)

        if not self.reversed_entry_id.transaction_ids:
            transaction_ids = (
                self.env["payment.transaction"]
                .sudo()
                .search([("invoice_ids", "in", self.reversed_entry_id.id)])
            )
        else:
            transaction_ids = self.reversed_entry_id.transaction_ids

        reference = transaction_ids.mapped("acquirer_reference")
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
            self.invoice_payment_state = "paid"
            self.message_post(body="Mollie payment refund has been generated.")
        except Exception as e:
            _logger.warning(e)

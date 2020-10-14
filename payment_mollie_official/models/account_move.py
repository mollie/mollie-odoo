# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    valid_for_mollie_refund = fields.Boolean(compute="_compute_valid_for_mollie_refund")
    mollie_refund_reference = fields.Char()

    def _compute_valid_for_mollie_refund(self):
        for move in self:
            has_mollie_tx = False
            if move.move_type == 'out_refund' and move._find_valid_mollie_transactions() and move.state == "posted" and move.payment_state != 'paid':
                has_mollie_tx = True
            move.valid_for_mollie_refund = has_mollie_tx

    def mollie_process_refund(self):
        self.ensure_one()
        mollie_transactions = self._find_valid_mollie_transactions()

        # TODO: Need to handle multiple transection
        if len(mollie_transactions) > 1:
            raise UserError(_("Multiple mollie transactions are linked with invoice. Please refund manually from mollie portal"))

        if mollie_transactions:

            # Create payment record and post the payment
            AccountPaymentRegister = self.env['account.payment.register'].with_context(active_ids=self.ids, active_model='account.move')
            payment_obj = AccountPaymentRegister.create({
                'journal_id': mollie_transactions.payment_id.journal_id.id,
                'payment_method_id': mollie_transactions.payment_id.payment_method_id.id
            })
            payment_obj.action_create_payments()

            # Create refund in mollie via API
            refund = mollie_transactions.acquirer_id._api_mollie_refund(self.amount_total, self.currency_id, mollie_transactions.acquirer_reference)
            if refund['status'] == 'refunded':
                self.mollie_refund_reference = refund['id']

    def _find_valid_mollie_transactions(self):
        self.ensure_one()
        return self.reversed_entry_id.transaction_ids.filtered(lambda tx: tx.state == 'done' and tx.acquirer_id.provider == 'mollie')

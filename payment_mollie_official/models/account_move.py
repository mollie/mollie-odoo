# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    valid_for_mollie_refund = fields.Boolean(compute="_compute_valid_for_mollie_refund")
    mollie_refund_reference = fields.Char()

    def _get_mollie_payment_data_for_refund(self):
        self.ensure_one()
        mollie_transactions = self._find_valid_mollie_transactions()
        if self.move_type == 'out_refund' and mollie_transactions:
            # TODO: Need to handle multiple transection
            if len(mollie_transactions) > 1:
                raise UserError(_("Multiple mollie transactions are linked with invoice. Please refund manually from mollie portal"))
            payment_record = mollie_transactions.acquirer_id._mollie_get_payment_data(mollie_transactions.acquirer_reference, force_payment=True)
            return payment_record, mollie_transactions
        return False, mollie_transactions

    def _compute_valid_for_mollie_refund(self):
        for move in self:
            has_mollie_tx = False
            if move.move_type == 'out_refund' and move._find_valid_mollie_transactions() and move.state == "posted":
                has_mollie_tx = True
            move.valid_for_mollie_refund = has_mollie_tx

    def mollie_process_refund(self):
        self.ensure_one()
        payment_record, mollie_transactions = self._get_mollie_payment_data_for_refund()
        if payment_record:
            # Create payment record and post the payment
            AccountPaymentRegister = self.env['account.payment.register'].with_context(active_ids=self.ids, active_model='account.move')
            payment_obj = AccountPaymentRegister.create({
                'journal_id': mollie_transactions.payment_id.journal_id.id,
                'payment_method_id': mollie_transactions.payment_id.payment_method_id.id
            })
            payment_obj.action_create_payments()
            # Create refund in mollie via API
            refund = mollie_transactions.acquirer_id._api_mollie_refund(self.amount_total, self.currency_id, payment_record)
            if refund['status'] == 'refunded':
                self.mollie_refund_reference = refund['id']

    def _find_valid_mollie_transactions(self):
        self.ensure_one()

        # CASE 1: For the credit notes generated from invoice
        transections = self.reversed_entry_id.transaction_ids.filtered(lambda tx: tx.state == 'done' and tx.acquirer_id.provider == 'mollie')

        # CASE 2: For the credit note generated due to returns of delivery
        # TODO: In this case credit note is generated from Sale order and so both invoice are not linked as reversal move.
        # this module does not have direct dependencies on the sales module. We are checking fields in move line to check sale order is linked.
        # and we get transections info from sale order. May be, we can create glue module for this.
        if not transections and 'sale_line_ids' in  self.invoice_line_ids._fields:
            transections = self.invoice_line_ids.mapped('sale_line_ids.order_id.transaction_ids')

        return transections

    def _post(self, soft=True):
        """ Vouchers might create extra payment record for reminder amount
            when 2 diffrent journal are there 2 payment records are created
            so we need to process second payment if present.
        """
        posted = super()._post(soft)

        for invoice in posted.filtered(lambda move: move.is_invoice()):
            payments = invoice.mapped('transaction_ids.mollie_reminder_payment_id')
            move_lines = payments.line_ids.filtered(lambda line: line.account_internal_type in ('receivable', 'payable') and not line.reconciled)
            for line in move_lines:
                invoice.js_assign_outstanding_line(line.id)
        return posted

    def action_register_refund_payment(self):
        context = {
            'active_model': 'account.move',
            'active_ids': self.ids,
        }

        payment_record, mollie_transactions = self._get_mollie_payment_data_for_refund()

        # We will not get `amountRemaining` key if payment is not paid (only authorized)
        if payment_record and payment_record.get('amountRemaining'):
            # TO-DO: check the case where amount is refunded in another currency or raise warning
            remaining_amount = float(payment_record['amountRemaining']['value'])
            if remaining_amount:
                context.update({
                    'default_journal_id': mollie_transactions.payment_id.journal_id.id,
                    'default_payment_method_id': mollie_transactions.payment_id.payment_method_id.id,
                    'default_amount': min(self.amount_residual, remaining_amount),
                    'default_is_mollie_refund': True,
                    'default_max_mollie_amount': remaining_amount,
                    'default_mollie_transecion_id': mollie_transactions.id
                })

        return {
            'name': _('Register Refund Payment'),
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'context': context,
            'target': 'new',
            'type': 'ir.actions.act_window',
        }
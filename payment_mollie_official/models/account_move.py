# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    valid_for_mollie_refund = fields.Boolean(compute="_compute_valid_for_mollie_refund")
    mollie_refund_reference = fields.Char()

    def _get_mollie_payment_data_for_refund(self):
        self.ensure_one()
        mollie_transactions = self._find_valid_mollie_transactions()
        if self.type == 'out_refund' and mollie_transactions:
            # TODO: Need to handle multiple transection
            if len(mollie_transactions) > 1:
                raise UserError(_("Multiple mollie transactions are linked with invoice. Please refund manually from mollie portal"))
            payment_record = mollie_transactions.acquirer_id._mollie_get_payment_data(mollie_transactions.acquirer_reference, force_payment=True)
            return payment_record, mollie_transactions
        return False, mollie_transactions

    def _compute_valid_for_mollie_refund(self):
        for move in self:
            has_mollie_tx = False
            if move.state == 'open' and move._find_valid_mollie_transactions():
                has_mollie_tx = True
            move.valid_for_mollie_refund = has_mollie_tx

    def mollie_process_refund(self):
        self.ensure_one()
        payment_record, mollie_transactions = self._get_mollie_payment_data_for_refund()
        if payment_record:
            # Create payment record and post the payment
            AccountPayment = self.env['account.payment'].with_context(active_ids=self.ids, active_model='account.invoice', active_id=self.id)
            vals = AccountPayment.default_get(['payment_type', 'partner_type', 'partner_id', 'amount', 'currency_id', 'payment_date', 'communication', 'payment_difference_handling', 'writeoff_label', 'journal_id', 'payment_method_id'])
            payment_obj = AccountPayment.create({
                'journal_id': mollie_transactions.payment_id.journal_id.id,
                'payment_method_id': mollie_transactions.payment_id.payment_method_id.id
            })
            payment_obj.action_validate_invoice_payment()

            # Create refund in mollie via API
            refund = mollie_transactions.acquirer_id._api_mollie_refund(self.amount_total, self.currency_id, payment_record)
            if refund['status'] in ['refunded', 'pending']:
                self.mollie_refund_reference = refund['id']

    def _find_valid_mollie_transactions(self):
        self.ensure_one()
        return self.refund_invoice_id.transaction_ids.filtered(lambda tx: tx.state == 'done' and tx.acquirer_id.provider == 'mollie')

    @api.multi
    def action_invoice_open(self):
        """ Vouchers might create extra payment record for reminder amount
            when 2 diffrent journal are there 2 payment records are created
            so we need to process second payment if present.
        """
        res = super(AccountInvoice, self).action_invoice_open()

        if not self:
            return res

        for invoice in self:
            payments = invoice.mapped('transaction_ids.mollie_reminder_payment_id')
            move_lines = payments.mapped('move_line_ids').filtered(lambda line: not line.reconciled and line.credit > 0.0)
            for line in move_lines:
                invoice.assign_outstanding_credit(line.id)

        return res

    def action_invoice_register_refund_payment(self):
        payment_record, mollie_transactions = self._get_mollie_payment_data_for_refund()
        context = dict(self.env.context)
        context['default_invoice_ids'] = [(4, context.get('active_id'), None)]
        context['active_model'] = 'account.invoice'
        context['active_id'] = self.id
        context['active_ids'] = [self.id]
        # We will not get `amountRemaining` key if payment is not paid (only authorized)
        if payment_record and payment_record.get('amountRemaining'):
            # TO-DO: check the case where amount is refunded in another currency or raise warning
            remaining_amount = float(payment_record['amountRemaining']['value'])
            if remaining_amount:
                default_context = {
                    'default_journal_id': mollie_transactions.payment_id.journal_id.id,
                    'default_payment_method_id': mollie_transactions.payment_id.payment_method_id.id,
                    'default_amount': min(self.residual, remaining_amount),
                    'default_is_mollie_refund': True,
                    'default_max_mollie_amount': remaining_amount,
                    'default_mollie_transecion_id': mollie_transactions.id
                }
                context.update(default_context)

        return {
            'name': _('Register Payment'),
            'res_model': 'account.payment',
            'view_mode': 'form',
            'view_id': self.env.ref('account.view_account_payment_invoice_form').id,
            'context': context,
            'target': 'new',
            'type': 'ir.actions.act_window',
        }
# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    is_mollie_refund = fields.Boolean()
    max_mollie_amount = fields.Float()
    mollie_transecion_id = fields.Many2one('payment.transaction')

    def action_create_payments(self):
        payments = super().action_create_payments()

        # Refund flow is only supported for a single Mollie refund wizard.
        if len(self) != 1 or not self.is_mollie_refund or not payments.get('res_id'):
            return payments

        # TO-DO: check the case where amount is refunded in another currency or raise warning
        if not self.max_mollie_amount:
            raise UserError(_("Full amount is already refunded for this payment"))
        if self.amount > self.max_mollie_amount:
            raise UserError(_("Maximum amount you can refund is %s. Please change the refund amount." % self.max_mollie_amount))

        refund_wizard = self.env['payment.refund.wizard'].create({
            'payment_id': self.mollie_transecion_id.payment_id.id,
            'amount_to_refund': self.amount,
        })

        result = refund_wizard.action_refund()
        refund_transaction_id = result.get('context', {}).get('mollie_refund_id')

        if not refund_transaction_id:
            return payments

        refund_transaction = self.env['payment.transaction'].browse(refund_transaction_id)
        invoice_ids = (
            self.env.context.get('active_ids', [])
            if self.env.context.get('active_model') == 'account.move'
            else []
        )
        refund_transaction.write({
            'payment_id': payments.get('res_id'),
            'invoice_ids': invoice_ids,
        })
        return payments

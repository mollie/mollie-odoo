# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    is_mollie_refund = fields.Boolean()
    max_mollie_amount = fields.Float()
    mollie_transecion_id = fields.Many2one('payment.transaction')

    def action_create_payments(self):
        payments = super().action_create_payments()

        # We assume there is one record
        if len(self) == 1 and self.is_mollie_refund:
            # TO-DO: check the case where amount is refunded in another currency or raise warning
            if not self.max_mollie_amount:
                raise UserError(_("Full amount is already refunded for this payment"))
            if self.amount > self.max_mollie_amount:
                raise UserError(_("Maximum amount you can refund is %s. Please change the refund amount." % self.max_mollie_amount))

            payment_record = self.mollie_transecion_id.acquirer_id._mollie_get_payment_data(self.mollie_transecion_id.acquirer_reference, force_payment=True)
            refund = self.mollie_transecion_id.acquirer_id._api_mollie_refund(self.amount, self.currency_id, payment_record)

            if refund['status'] in ['pending', 'refunded'] and payments.get('res_id'):
                description = refund['id']
                payment_record = self.env['account.payment'].browse(payments.get('res_id'))
                payment_record.write({'mollie_refund_reference': description})

                if payment_record.reconciled_invoice_ids and payment_record.reconciled_invoice_ids.mollie_refund_reference:
                    description = "%s,%s" % (payment_record.reconciled_invoice_ids.mollie_refund_reference, description)

                payment_record.reconciled_invoice_ids.write({'mollie_refund_reference': refund['id']})

            return True

        return payments


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    mollie_refund_reference = fields.Char()

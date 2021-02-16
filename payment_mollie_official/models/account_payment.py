# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    mollie_refund_reference = fields.Char()
    is_mollie_refund = fields.Boolean()
    max_mollie_amount = fields.Float()
    mollie_transecion_id = fields.Many2one('payment.transaction')

    def post(self):
        sup = super().post()

        # We assume there is one record
        if len(self) == 1 and self.is_mollie_refund:
            # TO-DO: check the case where amount is refunded in another currency or raise warning
            if not self.max_mollie_amount:
                raise UserError(_("Full amount is already refunded for this payment"))
            if self.amount > self.max_mollie_amount:
                raise UserError(_("Maximum amount you can refund is %s. Please change the refund amount." % self.max_mollie_amount))

            payment_record = self.mollie_transecion_id.acquirer_id._mollie_get_payment_data(self.mollie_transecion_id.acquirer_reference, force_payment=True)
            refund = self.mollie_transecion_id.acquirer_id._api_mollie_refund(self.amount, self.currency_id, payment_record)

            if refund['status'] in ['pending', 'refunded']:
                description = refund['id']
                self.write({'mollie_refund_reference': description})

                if self.reconciled_invoice_ids and self.reconciled_invoice_ids.mollie_refund_reference:
                    description = "%s,%s" % (self.reconciled_invoice_ids.mollie_refund_reference, description)
                self.reconciled_invoice_ids.write({'mollie_refund_reference': refund['id']})

        return sup

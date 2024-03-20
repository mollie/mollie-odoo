# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, fields


class AccountPaymentMethod(models.Model):
    _inherit = 'account.payment.method'

    @api.model
    def _get_payment_method_information(self):
        res = super()._get_payment_method_information()

        method_codes = self.env['payment.provider'].sudo()._get_all_mollie_methods_codes()  # no query for the performace
        for mollie_method_code in method_codes:
            res[f'mollie_{mollie_method_code}'] = {'mode': 'unique', 'domain': [('type', '=', 'bank')]}
        return res


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    mollie_refund_reference = fields.Char()

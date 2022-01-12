
# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    mollie_customer_id = fields.Char()

    def _mollie_validate_customer_id(self, acquirer):
        self.ensure_one()
        customer_id = self.sudo().mollie_customer_id
        if customer_id:
            customer_data = acquirer._api_get_customer_data(customer_id, silent_errors=True)
            if customer_data.get('status') == 410:    # customer ID deleted
                self.mollie_customer_id = False
# -*- coding: utf-8 -*-

from odoo import models


class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'mollie.terminal.payment.mixin']

    def _get_mollie_terminal_payment_context(self):
        context = super()._get_mollie_terminal_payment_context()
        context.update({
            'default_order_id': self.id,
        })
        return context

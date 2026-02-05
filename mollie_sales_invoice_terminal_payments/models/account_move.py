# -*- coding: utf-8 -*-

from odoo import models


class AccountMove(models.Model):

    _name = 'account.move'
    _inherit = ['account.move', 'mollie.terminal.payment.mixin']

    def _get_mollie_terminal_payment_context(self):
        context = super()._get_mollie_terminal_payment_context()
        context.update({
            'default_move_id': self.id
        })
        return context

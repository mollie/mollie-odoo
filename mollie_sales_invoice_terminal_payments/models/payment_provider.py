# -*- coding: utf-8 -*-

from odoo import models, fields, _


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    mollie_sale_order_terminal_payment_enabled = fields.Boolean(string='Terminal Payment From Sales')
    mollie_account_move_terminal_payment_enabled = fields.Boolean(string='Terminal Payment From Invoice')

    def _get_terminal_api_key(self):
        """
        Retrieve the appropriate Mollie API key based on the current state.

        This method ensures that the correct API key is returned depending on whether
        the instance is in 'test' or 'production' mode.

        If payment_mollie_official is installed then the instance has a 'mollie_api_key_test'
        field returned in test mode.

        Returns:
            str or bool: The appropriate Mollie API key if available, otherwise False.
        """
        self.ensure_one()
        mollie_api_key = self.mollie_api_key
        # to make it compatible with mollie_official module
        if self._fields.get('mollie_api_key_test') and self.state == 'test':
            mollie_api_key = self.mollie_api_key_test
        return mollie_api_key or False

    def action_open_terminal_list(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Mollie Terminals'),
            'res_model': 'mollie.payments.terminal',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('provider_id', '=', self.id)],
            'context': {'default_mollie_provider_id': self.id}
        }

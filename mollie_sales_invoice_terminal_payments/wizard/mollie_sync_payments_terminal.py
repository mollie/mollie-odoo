# -*- coding: utf-8 -*-

from odoo import fields, models


class MolliePaymentsSyncWizard(models.TransientModel):
    _name = 'sync.mollie.payments.terminal'
    _description = 'Mollie Payments Terminal Sync Wizard'

    def _default_mollie_api_key(self):
        if not self.env.context.get('default_mollie_provider_id'):
            return False
        return self.env['payment.provider'].browse(self.env.context['default_mollie_provider_id'])._get_terminal_api_key()

    mollie_api_key = fields.Char(default=_default_mollie_api_key)
    mollie_provider_id = fields.Many2one('payment.provider', string='Payment Provider')

    def sync_now(self):
        self.env['mollie.payments.terminal']._sync_mollie_terminals(self.mollie_provider_id)

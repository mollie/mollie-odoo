# -*- coding: utf-8 -*-

from odoo import fields, models


class MollieSyncWizard(models.TransientModel):
    _name = 'mollie.sync.wizard'
    _description = 'Mollie Sync Wizard'

    provider_id = fields.Many2one('payment.provider', required=True)
    reload_metadata = fields.Boolean(default=False, string='Reload Metadata')

    def action_confirm(self):
        self.ensure_one()
        self.env['payment.method'].with_context(reload_metadata=self.reload_metadata)._sync_mollie_methods(self.provider_id)
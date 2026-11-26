# -*- coding: utf-8 -*-

from odoo import api, fields, models


class MollieSyncWizard(models.TransientModel):
    _name = 'sync.mollie.terminal'
    _description = 'Mollie Terminal Sync Wizard'

    def _default_provider_id(self):
        providers = self.env['payment.provider'].search([('code', '=', 'mollie')])
        return providers if len(providers) == 1 else False

    provider_id = fields.Many2one(
        'payment.provider', string='Mollie Provider', required=True,
        domain="[('code', '=', 'mollie')]", default=_default_provider_id)
    api_key_set = fields.Boolean(compute='_compute_api_key_set')

    @api.depends('provider_id')
    def _compute_api_key_set(self):
        for wizard in self:
            wizard.api_key_set = wizard.provider_id._has_mollie_api_key()

    def sync_now(self):
        self.env['mollie.pos.terminal']._sync_mollie_terminals(provider_id=self.provider_id)

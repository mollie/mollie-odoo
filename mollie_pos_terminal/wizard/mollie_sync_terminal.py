# -*- coding: utf-8 -*-

from odoo import fields, models


class MollieSyncWizard(models.TransientModel):
    _name = 'sync.mollie.terminal'
    _description = 'Mollie Terminal Sync Wizard'

    def _default_mollie_terminal_api_key(self):
        return self.env.company.mollie_terminal_api_key

    mollie_terminal_api_key = fields.Char(default=_default_mollie_terminal_api_key)
    api_key_not_set = fields.Boolean(default=_default_mollie_terminal_api_key)

    def sync_now(self):
        self.env['mollie.pos.terminal']._sync_mollie_terminals()

# -*- coding: utf-8 -*-

from odoo import fields, models


class MollieSyncWizard(models.TransientModel):
    _name = 'sync.mollie.terminal'
    _description = 'Mollie Terminal Sync Wizard'

    def _default_api_key_set(self):
        # sudo: the key is restricted to base.group_system; here we only expose
        return bool(self.env.company.sudo().mollie_terminal_api_key)

    api_key_set = fields.Boolean(default=_default_api_key_set)

    def sync_now(self):
        self.env['mollie.pos.terminal']._sync_mollie_terminals()

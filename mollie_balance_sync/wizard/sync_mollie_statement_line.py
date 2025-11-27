# -*- coding: utf-8 -*-

from odoo import fields, models


class SyncMollieStatementLineWizard(models.TransientModel):
    _name = 'sync.mollie.statement.line'
    _description = 'Mollie Terminal Sync Wizard'

    def _default_remaining_mollie_transaction_count(self):
        return self.env['mollie.transaction.queue'].search_count([('state', '=', 'not_created')], limit=100)

    remaining_mollie_transaction_count = fields.Integer(default=_default_remaining_mollie_transaction_count)

    def sync_now(self):
        """create statement lines from queue"""
        self.env['mollie.transaction.queue']._cron_generate_mollie_statements_from_queue()

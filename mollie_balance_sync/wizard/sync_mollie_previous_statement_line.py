# -*- coding: utf-8 -*-

from odoo import fields, models


class SyncMolliePreviousStatementLineWizard(models.TransientModel):
    _name = 'sync.mollie.previous.statement.line'
    _description = 'Sync Mollie Previous Statement Line'

    date_begin = fields.Datetime('Date Begin', required=True)
    date_end = fields.Datetime('Date End', required=True)

    def sync_previous_statement_line(self):
        journal_id = self.env['account.journal'].browse(self.env.context.get('active_id'))
        journal_id._sync_mollie_previous_balance_statement(self.date_begin, self.date_end)

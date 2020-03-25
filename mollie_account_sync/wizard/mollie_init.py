# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

LIMIT = 40


class MollieInit(models.TransientModel):
    _name = 'wiz.mollie.init'
    _description = 'Mollie init wizzrd'

    def _default_settlement_lines(self):
        journal_id = self.env.context.get('default_journal_id')
        result = []
        if journal_id:
            journal = self.env['account.journal'].browse(journal_id)
            settlements_data = journal._api_get_settlements(limit=LIMIT)
            if settlements_data['count'] == 0:
                return []
            last_bnk_stmt = self.env['account.bank.statement'].search([('journal_id', '=', journal_id)], limit=1)
            for settlement in settlements_data['_embedded']['settlements']:
                settlement_date = journal._format_mollie_date(settlement['createdAt'])
                settlement_date_obj = fields.Date.to_date(settlement_date)
                if (not last_bnk_stmt or settlement_date_obj > last_bnk_stmt.date) and settlement['status'] == 'paidout':
                    result.append((0, 0, {
                        'name': settlement['reference'],
                        'settlement_date': settlement_date,
                        'settlement_id': settlement['id'],
                        'settlement_amount': settlement['amount']['value'],
                    }))
        return result

    settlement_lines = fields.One2many('wiz.mollie.init.line', 'wiz_id', default=_default_settlement_lines)
    journal_id = fields.Many2one('account.journal')
    sync_all = fields.Boolean()

    @api.onchange('sync_all')
    def on_change_sync_all(self):
        for line in self.settlement_lines:
            line.do_sync = self.sync_all

    def sync_settlement(self):
        self.ensure_one()
        line_to_sync = self.settlement_lines.filtered('do_sync')
        journal = self.journal_id
        if line_to_sync and journal:
            settlements_data = self.journal_id._api_get_settlements(limit=LIMIT)
            mollie_ids_to_sync = line_to_sync.mapped('settlement_id')

            new_list = []
            if settlements_data['count'] == 0:
                return []

            for settlement in settlements_data['_embedded']['settlements']:
                if settlement['id'] in mollie_ids_to_sync:
                    new_list.append(settlement)
            settlements_data['_embedded']['settlements'] = new_list
            settlements_data['count'] = len(new_list)
            if new_list:
                journal._process_settlements(settlements_data)
                journal.mollie_last_sync = fields.Datetime.now()


class MollieInitLines(models.TransientModel):
    _name = 'wiz.mollie.init.line'
    _description = 'Mollie init lines'

    wiz_id = fields.Many2one('wiz.mollie.init')
    name = fields.Char()
    settlement_date = fields.Date()
    settlement_id = fields.Char()
    settlement_amount = fields.Float()
    do_sync = fields.Boolean(string="Sync")

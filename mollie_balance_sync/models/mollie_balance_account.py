# -*- coding: utf-8 -*-

from odoo import fields, models


class MollieBalanceAccount(models.Model):
    _name = "mollie.balance.account"
    _description = 'mollie balance account'

    name = fields.Char('Name')
    bank_account_number = fields.Char('Bank Account')
    bank_account_id = fields.Char('bank Account Id')
    balance_id = fields.Char('Balance Id')
    journal_id = fields.Many2one('account.journal', string='Journal')

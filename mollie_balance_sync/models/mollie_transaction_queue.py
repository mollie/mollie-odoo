# -*- coding: utf-8 -*-
import json

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT


class MollieTransactionQueue(models.Model):
    _name = "mollie.transaction.queue"
    _description = 'mollie transaction queue'
    _order = 'transaction_date desc, id desc'

    transaction_date = fields.Datetime('Date')
    payment_ref = fields.Char('Payment Ref')
    transaction_id = fields.Char('Transaction Id')
    balance_transaction_id = fields.Char('Balance Transaction Id')
    amount = fields.Monetary('Amount')
    journal_id = fields.Many2one('account.journal', string='Journal')
    currency_id = fields.Many2one('res.currency', related="journal_id.currency_id")
    state = fields.Selection([
        ('not_created', 'Not Created'),
        ('created', 'Statement Created'),
        ('reconciled', 'Statement Reconciled'),
    ], compute='_compute_queue_state', string='Statement States', store=True)
    transaction_json = fields.Char('Transactions')
    statement_line_ids = fields.One2many('account.bank.statement.line', 'mollie_queue_id', string='Statement Line')
    reason_of_exception = fields.Char('Reason Of Exception')

    @api.depends('statement_line_ids', 'statement_line_ids.is_reconciled')
    def _compute_queue_state(self):
        """
        not_created: statement line not created
        created: statement line created
        reconciled: queue related statement line reconciled
        """
        for line in self:
            if line.statement_line_ids:
                if line.statement_line_ids[0].is_reconciled:
                    line.state = 'reconciled'
                else:
                    line.state = 'created'
            else:
                line.state = 'not_created'

    def _cron_generate_mollie_statements_from_queue(self):
        """ This method create bank statement lines from queue
        first 100 not created queue line at a time
        """
        transaction_queue = self.search([('state', '=', 'not_created')], order='transaction_date asc', limit=100)
        transaction_line_data = {}
        for line in transaction_queue:
            key = line.journal_id
            transaction_line_data.setdefault(key, self.env['mollie.transaction.queue'])
            transaction_line_data[key] += line

        for journal, lines in transaction_line_data.items():
            self._create_bank_statements_from_queue(journal, lines)

    def _create_bank_statements_from_queue(self, journal, transaction_queue):
        """
        :journal: journal record for create statement line
        :transaction_queue: transaction queue records for create statement lines
        """
        transaction_lines = []
        for line in transaction_queue:
            transaction_line = {
                'date': line.transaction_date.strftime(DEFAULT_SERVER_DATE_FORMAT),
                'payment_ref': line.payment_ref,
                'amount': line.amount,
                'mollie_transaction_id': line.transaction_id,
                'journal_id': line.journal_id.id,
                'mollie_queue_id': line.id
            }
            if line.transaction_json:
                transaction_line.update(line._prepare_extra_queue_data())
            transaction_lines.append(transaction_line)
        if transaction_lines:
            self.env['account.bank.statement.line'].create(transaction_lines)

    # set metadata from transaction queue line, payment ref, partner
    def _prepare_extra_queue_data(self):
        """update transaction lines
        :return dict: metadata, orderId, partner, payment reference
        """
        self.ensure_one()
        extra_data = {}
        mollie_acquires = self.env['payment.provider'].search([('code', '=', 'mollie')])
        json_info = json.loads(self.transaction_json)
        json_info['MollieType'] = self.payment_ref
        json_info['balance_transaction_id'] = self.balance_transaction_id
        payment_data = self._api_get_transaction_data(json_info)
        if payment_data:
            if payment_data.get('metadata'):
                json_info.update(payment_data['metadata'])
            if payment_data.get('orderId'):
                json_info['mollie_order_id'] = payment_data.get('orderId')

            if json_info:
                extra_data['mollie_balance_json_info'] = json.dumps(json_info)
                payment_ref = self._generate_balance_payment_ref(payment_data, json_info['MollieType'])
                if payment_ref:
                    extra_data['payment_ref'] = payment_ref

            domain = [('provider_reference', '=', payment_data['id'])]
            if mollie_acquires:
                domain += [('provider_id', 'in', mollie_acquires.ids)]
            transaction = self.env['payment.transaction'].search(domain, limit=1)
            if transaction and transaction.partner_id:
                extra_data['partner_id'] = transaction.partner_id.id

            self._set_custom_extra_data(payment_data, extra_data)

        return extra_data

    def _set_custom_extra_data(self, payment_data, extra_data):
        """ Abstract method for overriding purposes
            you can directy update extra_data if you want
        """
        return True

    def _generate_balance_payment_ref(self, payment_data, tx_type):
        """generate payment reference
        :payment_data dict: payment data from mollie api
        :tx_type str: transaction type
        :return str: payment reference
        """
        metadata = payment_data.get('metadata') or {}
        ref = ""
        if metadata.get('reference'):
            ref = '-'.join([metadata.get('reference'), tx_type])
            if metadata.get('transaction_id'):
                ref += '- #' + str(metadata.get('transaction_id'))
        if not ref:
            if payment_data.get('description'):
                ref = payment_data.get('description')
            else:
                ref = tx_type + ' for ' + payment_data['id']
        return ref

    def unlink(self):
        if self.filtered_domain([('state', '=', 'reconciled')]):
            raise ValidationError(_('You cannot delete lines with reconciled statements.'))
        self.mapped('statement_line_ids').unlink()
        return super().unlink()

    def action_generate_statement_lines_from_queue(self):
        """open wizard for generate statement lines"""
        return {
            "name": _("Generate Statements"),
            "type": "ir.actions.act_window",
            "res_model": "sync.mollie.statement.line",
            "target": "new",
            "views": [[False, "form"]],
            "context": {"is_modal": True},
        }

    # =================
    # API CALLS METHODS
    # =================

    def _api_get_transaction_data(self, transaction_json):
        """ Fetch transaction data from mollie api"""
        transaction_data = {}
        if transaction_json and transaction_json.get('paymentId'):
            api_endpoint = f"/payments/{transaction_json['paymentId']}"
            transaction_data = self.journal_id._mollie_api_server_call(api_endpoint)
            if transaction_data.get('error'):
                self.reason_of_exception = transaction_data.get('error')
                return {}
        return transaction_data

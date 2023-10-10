# -*- coding: utf-8 -*-

import json
import logging
import pytz
import requests

from datetime import datetime
from werkzeug import urls

from odoo import _, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)

TIMEOUT = 20
LIMIT = 250


class AccountJournal(models.Model):

    _inherit = "account.journal"

    mollie_api_key = fields.Char(string="Mollie Organisation Access token", copy=False)
    mollie_last_sync = fields.Datetime(copy=False)
    mollie_balance_account_id = fields.Many2one('mollie.balance.account', string='Balance Account', copy=False)
    mollie_sync_from = fields.Datetime('Sync From', copy=False)
    mollie_initialize = fields.Boolean('Mollie Initialize', copy=False)
    mollie_queue_statement_count = fields.Integer(compute='_compute_mollie_queue_statement_count', string='Mollie Queue Statement Count')

    def _compute_mollie_queue_statement_count(self):
        # TODO: improve this
        for journal in self:
            journal.mollie_queue_statement_count = self.env['mollie.transaction.queue'].search_count([
                ('journal_id', '=', journal.id),
                ('state', '=', 'not_created'),
            ])

    def __get_bank_statements_available_sources(self):
        """ Adding new source for statement """
        available_sources = super(AccountJournal, self).__get_bank_statements_available_sources()
        available_sources.append(("mollie_balance_sync", _("Mollie Balance Synchronization")))
        return available_sources

    def action_sync_mollie_balance_account(self):
        """ This method fetches balance account details from the mollie and
        Creates `mollie.balance.account` record in odoo"""

        list_balances = self._mollie_api_server_call('/balances')
        if not list_balances.get('count'):
            return

        mollie_balance_accounts = []
        BalanceAccount = self.env['mollie.balance.account']
        existing_mollie_balance_accounts = BalanceAccount.search([('journal_id', '=', self.id)]).mapped('balance_id')
        for balance_acc in list_balances['_embedded']['balances']:
            if balance_acc['id'] not in existing_mollie_balance_accounts:
                transferDestination = balance_acc['transferDestination']
                mollie_balance_accounts.append({
                    'name': transferDestination['beneficiaryName'],
                    'bank_account_number': transferDestination['bankAccount'],
                    'bank_account_id': transferDestination.get('bankAccountId') or '',
                    'balance_id': balance_acc['id'],
                    'journal_id': self.id
                })
        if mollie_balance_accounts:
            BalanceAccount.create(mollie_balance_accounts)

    def _get_mollie_last_sync_transaction(self):
        """ Return the last synced transaction in the queue for given journal account """
        self.ensure_one()
        return self.env['mollie.transaction.queue'].search([('journal_id', '=', self.id)], limit=1)

    def _cron_sync_mollie_balance_statement(self):
        """ This method will be called via cron to create balance transactions periodically"""
        journal_ids = self.search([('bank_statements_source', '=', 'mollie_balance_sync'), ('mollie_api_key', '!=', False)])
        for journal in journal_ids:
            journal._sync_mollie_balance()

    def _sync_mollie_balance(self):
        """ This method push new balance transactions to queue"""
        if self.mollie_balance_account_id and self.mollie_balance_account_id.balance_id:
            last_transaction = self._get_mollie_last_sync_transaction()
            if last_transaction:
                balance_id = self.mollie_balance_account_id.balance_id
                balance_url = f"/balances/{balance_id}/transactions?limit={LIMIT}"
                transaction_lines = self._get_mollie_balance_transaction_recursive(balance_url, last_transaction_id=last_transaction.balance_transaction_id)
                if transaction_lines:
                    self._create_mollie_transaction_queue(transaction_lines)
                self.mollie_last_sync = fields.Datetime.now()

    def action_mollie_balance_initial_sync(self):
        """ This method will be called first time you start sync """
        last_transaction = self._get_mollie_last_sync_transaction()
        if last_transaction:
            raise UserError(_('You can not initialize mollie balance journal twice'))

        if not self.mollie_sync_from:
            raise UserError(_('Select sync from date in journal (%s).' % self.name))

        balance_id = self.mollie_balance_account_id.balance_id
        balance_url = f"/balances/{balance_id}/transactions?limit={LIMIT}"
        transaction_lines = self._get_mollie_balance_transaction_recursive(balance_url, sync_from_date=self.mollie_sync_from)
        if transaction_lines:
            self._create_mollie_transaction_queue(transaction_lines)
            self.mollie_last_sync = fields.Datetime.now()
            self.mollie_initialize = True

    def _get_mollie_balance_transaction_recursive(self, balance_url, sync_from_date=None, last_transaction_id=None):
        """ This method used to fetch balance transaction recursively

            You must pass sync_from_date or last_transaction_id to stop recursive calls.
        """
        if not sync_from_date and not last_transaction_id:
            raise UserError(_('Method needs at least one stopping pointes'))

        transaction_lines = []
        transactions_response = self._mollie_api_server_call(balance_url)
        if transactions_response and transactions_response.get('count'):
            transactions = transactions_response['_embedded']['balance_transactions']

            for transaction in transactions:
                transaction_id = self._get_transaction_id(transaction)
                transaction_date = self._parse_mollie_date(transaction['createdAt'])
                if (last_transaction_id == transaction['id']) or (sync_from_date and sync_from_date > transaction_date):
                    break

                amount = float(transaction['initialAmount']['value'])

                if transaction.get('deductions'):
                    transaction_lines += [{
                        'balance_transaction_id': transaction['id'],
                        'transaction_date': transaction_date,
                        'payment_ref': ' '.join(['deductions :', transaction['type'], '#' + transaction_id]),
                        'amount': float(transaction['deductions']['value']),
                        'transaction_id': transaction_id,
                        'journal_id': self.id
                    }]

                if amount != 0.0:
                    transaction_lines += [{
                        'balance_transaction_id': transaction['id'],
                        'transaction_date': transaction_date,
                        'payment_ref': transaction['type'],
                        'amount': float(transaction['initialAmount']['value']),
                        'transaction_id': transaction_id,
                        'journal_id': self.id,
                        'transaction_json': json.dumps(transaction['context'] or {})
                    }]
            else:
                links = transactions_response.get('_links')
                if links and links.get('next'):
                    next_balance_url = links.get('next')['href'].split('/v2/')[-1]
                    transaction_lines += self._get_mollie_balance_transaction_recursive(next_balance_url, sync_from_date=sync_from_date, last_transaction_id=last_transaction_id)
        return transaction_lines

    def _create_mollie_transaction_queue(self, transaction_vals):
        """ This method create records for the transaction queue """
        if not transaction_vals:
            return
        transaction_vals.reverse()
        self.env['mollie.transaction.queue'].create(transaction_vals)

    # =====================
    # GENERIC TOOLS METHODS
    # =====================

    def _parse_mollie_date(self, date_str):
        tz_time = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S%z")
        return tz_time.replace(tzinfo=None)

    def _get_transaction_id(self, transaction):
        transaction_id = ''
        if transaction['type'] in ['payment', 'unauthorized-direct-debit', 'failed-payment', 'chargeback-reversal', 'application-fee', 'split-payment']:
            transaction_id = transaction['context']['paymentId']
        elif transaction['type'] in ['capture']:
            transaction_id = transaction['context']['captureId']
        elif transaction['type'] in ['refund', 'returned-refund', 'platform-payment-refund']:
            transaction_id = transaction['context']['refundId']
        elif transaction['type'] in ['chargeback', 'platform-payment-chargeback']:
            transaction_id = transaction['context']['chargebackId']
        elif transaction['type'] in ['outgoing-transfer', 'canceled-outgoing-transfer', 'returned-transfer']:
            transaction_id = transaction['context']['transferId']
        elif transaction['type'] in ['invoice-compensation']:
            transaction_id = transaction['context']['invoiceId']
        return transaction_id

    def _get_mollie_api_key(self, bearer=True):
        if not self.mollie_api_key:
            return False
        api_key = ''
        if bearer:
            api_key += 'Bearer '
        return api_key + self.mollie_api_key

    def _mollie_api_server_call(self, endpoint):
        self.ensure_one()
        endpoint = f'/v2/{endpoint.strip("/")}'
        url = urls.url_join('https://api.mollie.com/', endpoint)
        headers = {
            'content-type': 'application/json',
            'Authorization': self._get_mollie_api_key()
        }
        _logger.info('Mollie SYNC CALL on: %s', endpoint)

        try:
            req = requests.get(url, timeout=TIMEOUT, headers=headers)
            req.raise_for_status()
            return req.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            _logger.error('Mollie SYNC issue: %s', e)
            raise UserError(_('Some thing went wrong please try again after some time.'))
        except requests.exceptions.HTTPError as e:
            _logger.error('Mollie SYNC issue: %s', e)
            if req.status_code == 404 and endpoint.startswith('/v2/payments/'):
                return {'error': req.reason}
            raise UserError(_("MOLLIE: \n %s" % req.reason))


class AccountBankStatement(models.Model):
    _inherit = "account.bank.statement"

    journal_sync_type = fields.Selection(related="journal_id.bank_statements_source")


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    mollie_balance_json_info = fields.Char()
    mollie_transaction_id = fields.Char()
    mollie_queue_id = fields.Many2one('mollie.transaction.queue', string='Mollie Queue')

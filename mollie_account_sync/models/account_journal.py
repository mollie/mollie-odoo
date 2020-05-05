# -*- coding: utf-8 -*-

import json
import logging
import requests
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)

TIMEOUT = 20
API_DEBUG = False


class AccountJournal(models.Model):

    _inherit = "account.journal"

    mollie_api_key = fields.Char()
    mollie_test = fields.Boolean()
    mollie_last_sync = fields.Datetime()
    mollie_init_done = fields.Boolean()
    mollie_transfer_id = fields.Many2one('account.journal')
    need_transfer_count = fields.Integer(compute='_compute_transfer_count')

    def _compute_transfer_count(self):
        for journal in self:
            if journal.bank_statements_source == 'mollie_sync':
                journal.need_transfer_count = self.env['account.payment'].search_count([
                    ('payment_type', '=', 'transfer'),
                    ('journal_id', '=', journal.id),
                    ('state', '=', 'draft')
                ])
            else:
                journal.need_transfer_count = 0

    def __get_bank_statements_available_sources(self):
        """ Adding new source for statement """
        available_sources = super(AccountJournal, self).__get_bank_statements_available_sources()
        available_sources.append(("mollie_sync", _("Mollie Synchronization")))
        return available_sources

    def action_sync_mollie_statement(self):
        """ Entry point of execution.
            Only call this if journal is having type bank and source is "mollie_sync"
        """
        self.ensure_one()
        if self.bank_statements_source != 'mollie_sync':
            raise UserError(_('This method only call for mollie journals'))
        if not self.mollie_api_key:
            raise UserError(_('Please add API key for mollie'))

        # Just For testing account (This is not based on test account)
        if self.mollie_test and API_DEBUG:
            payment_data = self._mollie_api_call('https://api.mollie.com/v2/payments?limit=3')['_embedded']['payments']
            refund_data = self._mollie_api_call('https://api.mollie.com/v2/refunds?limit=1')['_embedded']['refunds']
            settlement = {
                'reference': "TEST 123123",
                'createdAt': "2020-02-29T04:30:00+00:00"
            }
            self._create_bank_statements(payment_data, refund_data, settlement)

        if self.mollie_test:
            return

        # Open wizard to choose settlement
        return self._action_sync_settlements()

    def _action_sync_settlements(self):
        return {
            'name': _('Sync mollie'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'wiz.mollie.init',
            'type': 'ir.actions.act_window',
            'context': {'default_journal_id': self.id},
            'view_id': self.env.ref('mollie_account_sync.mollie_init_view_form').id,
            'target': 'new'
        }

    def action_open_transfers(self):
        return {
            'name': _('Mollie Transfers'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.payment',
            'type': 'ir.actions.act_window',
            'domain': [
                ('payment_type', '=', 'transfer'),
                ('journal_id', '=', self.id),
                ('state', '=', 'draft')
            ],
        }

    def _process_settlements(self, settlements_data):
        """ Process settlements data received from mollie API.
            - This method fetch the payment and refund information for settlement.
            And then forward to next method.
            - It does not proccess it settlement is already synced.

            :param settlements_data: list of settlements data received from mollie API
        """
        if settlements_data['count'] == 0:
            return
        settlements_data['_embedded']['settlements'].reverse()
        BankStatement = self.env['account.bank.statement']
        for settlement in settlements_data['_embedded']['settlements']:
            # TODO: Manage chargeback
            exist = BankStatement.search([('mollie_settlement_id', '=', settlement['id'])], limit=1)
            if exist:
                continue
            if settlement['status'] != 'paidout':
                continue
            payment_data = self._api_get_settlement_payments(settlement['id'])
            refund_data = self._api_get_settlement_refunds(settlement['id'])
            self._create_bank_statements(payment_data, refund_data, settlement)

    def _create_bank_statements(self, payment_data, refund_data, settlement_data, return_lines=False):
        """ Create new bank statement based on settlement, settlement payments and settlement refunds.

            This method also try to guess the partner for statement.

            :param payment_data: list of payments data for given settlement.
            :param refund_data: list of refund data for given settlement.
            :param settlement_data: settlement information.
        """
        mollie_acquirer = self.env.ref('payment_mollie_official.payment_acquirer_mollie')
        BankStatement = self.env['account.bank.statement']
        statement_lines = []
        for payment in payment_data:
            if not payment.get('settlementAmount'):
                continue
            json_info = {}
            statement_line = {
                'date': self._format_mollie_date(payment['createdAt']),
                'name': self._generate_payment_ref(payment['metadata']) or payment['description'],
                'ref': payment['description'],
                'amount': float(payment['settlementAmount']['value']),
                'mollie_transaction_id': payment['id'],

            }
            if payment.get('metadata'):
                json_info.update(payment['metadata'])
            if payment.get('orderId'):
                json_info['mollie_order_id'] = payment.get('orderId')
            if len(json_info.keys()):
                statement_line['mollie_json_info'] = json.dumps(json_info)

            transaction = self.env['payment.transaction'].search([('acquirer_reference', '=', payment['id']), ('acquirer_id', '=', mollie_acquirer.id)], limit=1)
            if transaction and transaction.partner_id:
                statement_line['partner_id'] = transaction.partner_id.id
            statement_lines.append((0, 0, statement_line))
        for refund in refund_data:
            if not refund.get('settlementAmount'):
                continue
            statement_line = {
                'date': self._format_mollie_date(refund['createdAt']),
                'name': self._generate_payment_ref(refund['metadata']) or refund['description'],
                'ref': refund['description'],
                'amount': float(refund['settlementAmount']['value']),
                'mollie_transaction_id': refund['id'],
            }
            statement_lines.append((0, 0, statement_line))
        for fee_line in self.get_payment_fees_lines(settlement_data)['lines']:
            statement_lines.append((0, 0, fee_line))

        statement_vals = {
            'name': settlement_data['reference'],
            'date': self._format_mollie_date(settlement_data['createdAt']),
            'journal_id': self.id,
            'line_ids': statement_lines,
            'balance_start': self.env["account.bank.statement"]._get_opening_balance(self.id),
            'mollie_settlement_id': settlement_data['id'],
        }

        if self.mollie_transfer_id:
            manual_method = self.outbound_payment_method_ids.filtered(lambda m: m.code == 'manual')
            if not manual_method:
                raise UserError(_('Please enable Outgoing Payments mehtod "Manual" for this journal.'))
            manual_method = manual_method[0]

            statement_lines.append((0, 0, {
                'date': self._format_mollie_date(settlement_data['createdAt']),
                'name': 'MOLLIE PAYMENTS REF %s (for Internal Transfer)' % (settlement_data['reference']),
                'ref': 'MOLLIE PAYMENTS REF %s' % (settlement_data['reference']),
                'amount': - float(settlement_data['amount']['value']),
            }))

            transfer_id = self.env['account.payment'].create({
                'name': 'Internal Transfer Mollie ref: %s' % (settlement_data['reference']),
                'payment_type': 'transfer',
                'amount': float(settlement_data['amount']['value']),
                'journal_id': self.id,
                'destination_journal_id': self.mollie_transfer_id.id,
                'communication': 'Internal Transfer Mollie ref: %s' % (settlement_data['reference']),
                'payment_method_id': manual_method.id
            })
            statement_vals['mollie_internal_transfer_id'] = transfer_id.id
        if return_lines:
            return statement_vals
        statement = BankStatement.create(statement_vals)
        statement.balance_end_real = statement.balance_end

        # FIX Rounding issues
        diff = statement.balance_start - statement.balance_end_real
        if diff >= -0.05 and diff <= 0.05 and diff != 0:
            line_data = [(4, l.id, 0) for l in statement.line_ids]
            last_line = statement.line_ids[-1]
            line_data.append((0, 0, {
                'date': last_line.date,
                'name': 'Mollie rounding difference',
                'ref': 'Mollie rounding difference',
                'amount': diff
            }))
            statement.line_ids = line_data
            statement.balance_end_real = statement.balance_end

    def recheck_all_statements(self):
        '''Just to migrate old data to new one'''
        settlements_data = self._api_get_settlements(limit=25)
        if settlements_data['count'] == 0:
            return []
        settlement_dict = {}
        for settlement in settlements_data['_embedded']['settlements']:
            settlement_dict[settlement['id']] = settlement
        statements = self.env['account.bank.statement'].search([('journal_id', '=', self.id)]).sorted('date')
        previous_statement_amount = 0
        for stat in statements:
            if stat.line_ids.filtered(lambda s: (s.name).startswith('Fees ')):
                stat.balance_start = previous_statement_amount
                stat.balance_end_real = stat.balance_end
                previous_statement_amount = stat.balance_end_real
                continue
            settelement_data = settlement_dict.get(stat.mollie_settlement_id)
            if settelement_data:
                payment_data = self._api_get_settlement_payments(settelement_data['id'])
                refund_data = self._api_get_settlement_refunds(settelement_data['id'])
                mollie_transaction_ids = []
                new_lines = []

                # USD fix
                usd_lines = []
                for payment in payment_data:
                    if payment.get('amount', {}).get('currency') == 'USD':
                        usd_lines.append(payment['id'])

                for line in self._create_bank_statements(payment_data, refund_data, settelement_data, return_lines=True).get('line_ids', []):
                    if line[2].get('mollie_transaction_id') and line[2].get('mollie_transaction_id') not in usd_lines:
                        mollie_transaction_ids.append(line[2]['mollie_transaction_id'])
                    else:
                        new_lines.append(line)

                valid_lines = []
                for s_line in stat.line_ids:
                    if s_line.mollie_transaction_id and s_line.mollie_transaction_id not in mollie_transaction_ids:
                        if s_line.state != 'confirm' and s_line.journal_entry_ids:
                            s_line.button_cancel_reconciliation()
                        s_line.unlink()
                    else:
                        valid_lines.append(s_line.id)

                line_data = [(4, l, 0) for l in valid_lines]
                line_data.extend(new_lines)
                stat.line_ids = line_data
                stat.balance_start = previous_statement_amount
                stat.balance_end_real = stat.balance_end

                # FIX Rounding issues
                diff = stat.balance_start - stat.balance_end_real
                if diff >= -0.05 and diff <= 0.05 and diff != 0:
                    line_data = [(4, l, 0) for l in stat.line_ids.ids]
                    last_line = stat.line_ids[-1]
                    line_data.append((0, 0, {
                        'date': last_line.date,
                        'name': 'Mollie rounding difference',
                        'ref': 'Mollie rounding difference',
                        'amount': diff
                    }))
                    stat.line_ids = line_data
                    stat.balance_start = previous_statement_amount
                    stat.balance_end_real = stat.balance_end

            previous_statement_amount = stat.balance_end_real

    # =================
    # API CALLS METHODS
    # =================

    def _api_get_settlements(self, limit=None):
        """ Fetch settlements data from mollie api"""
        api_endpoint = "https://api.mollie.com/v2/settlements"
        if limit:
            api_endpoint += '?limit=' + str(limit)
        return self._mollie_api_call(api_endpoint)

    def _api_get_settlement_payments(self, settlement_id):
        """ Fetch settlements data from mollie api"""
        api_endpoint = "https://api.mollie.com/v2/settlements/%s/payments" % settlement_id
        payment_data = self._api_call_payments_recursive(api_endpoint)
        return payment_data

    def _api_call_payments_recursive(self, api_endpoint):
        payments = []
        payment_data = self._mollie_api_call(api_endpoint)
        if payment_data and payment_data['count'] > 0:
            payments.extend(payment_data['_embedded']['payments'])
        if payment_data["_links"]['next']:
            next_payments = self._api_call_payments_recursive(payment_data["_links"]['next']['href'])
            payments.extend(next_payments)
        return payments

    def _api_get_settlement_refunds(self, settlement_id):
        """ Fetch settlements data from mollie api"""
        api_endpoint = "https://api.mollie.com/v2/settlements/%s/refunds" % settlement_id
        refund_data = self._api_call_refunds_recursive(api_endpoint)
        return refund_data

    def _api_call_refunds_recursive(self, api_endpoint):
        refunds = []
        refund_data = self._mollie_api_call(api_endpoint)
        if refund_data and refund_data['count'] > 0:
            refunds.extend(refund_data['_embedded']['refunds'])
        if refund_data["_links"]['next']:
            next_refunds = self._api_call_refunds_recursive(refund_data["_links"]['next']['href'])
            refunds.extend(next_refunds)
        return refunds

    def _api_call_get_order_meta(self, order_id):
        api_endpoint = "https://api.mollie.com/v2/orders/%s" % order_id
        order = self._mollie_api_call(api_endpoint)
        data = {}
        if order.get('metadata'):
            data.update(order['metadata'])
        if order.get('billingAddress'):
            data.update(order['billingAddress'])
        return data

    # =====================
    # GENERIC TOOLS METHODS
    # =====================

    def _get_mollie_api_key(self, bearer=True):
        if not self.mollie_api_key:
            return False
        api_key = ''
        if bearer:
            api_key += 'Bearer '
        return api_key + self.mollie_api_key

    def _mollie_api_call(self, api_endpoint):
        headers = {
            'content-type': 'application/json',
            'Authorization': self._get_mollie_api_key()
        }
        _logger.info('Mollie SYNC CALL on: %s', api_endpoint)
        try:
            req = requests.get(api_endpoint, timeout=TIMEOUT, headers=headers)
            req.raise_for_status()
            return req.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
            _logger.error('Mollie SYNC issue: %s', e)
            raise UserError(_('Some thing went wrong please try again after some time.'))

    def _format_mollie_date(self, date_str):
        return datetime.strftime(datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S+00:00"), '%Y-%m-%d')

    def _generate_payment_ref(self, metadata):
        metadata = metadata or {}
        ref = ""
        if metadata.get('customer'):
            if metadata['customer'].get('firstName'):
                ref += metadata['customer']['firstName']
            if metadata['customer'].get('lastName'):
                if ref:
                    ref += ' '  # space for first and last name
                ref += metadata['customer']['lastName']
        if metadata.get('reference'):
            if ref:
                ref += ' #'  # space
            else:
                ref += '#'  # space
            ref += metadata['reference']
        return ref

    def get_payment_fees_lines(self, settlement_data):

        def l_round(amount):
            return amount

        lines = []
        total = 0
        for year in settlement_data['periods']:
            for month in settlement_data['periods'][year]:
                for fee in settlement_data['periods'][year][month].get('costs', []):
                    line_name = 'Fees %s (%s payment%s)' % (fee.get('description', ''), fee['count'], ('s' if fee['count'] > 1 else ''))
                    amount = - float(fee['amountGross']['value'])
                    lines.append({
                        'date': '%s-%s-01' % (year, month),
                        'name': line_name,
                        'ref': line_name,
                        'amount': l_round(amount)
                    })
                    total += l_round(amount)
        return {
            'amount': total,
            'lines': lines
        }


class AccountBankStatement(models.Model):
    _inherit = "account.bank.statement"

    mollie_settlement_id = fields.Char(index=True)
    journal_sync_type = fields.Selection(related="journal_id.bank_statements_source")
    mollie_internal_transfer_id = fields.Many2one('account.payment')

    # TODO: Add unique constraint for mollie_settlement_id

    def unlink(self):
        for statement in self:
            if statement.mollie_internal_transfer_id and statement.mollie_internal_transfer_id.state not in ['draft', 'cancelled']:
                raise UserError(_('[Mollie] You cannot delete statement with confirmed internal transfer'))
        transfers = self.mapped('mollie_internal_transfer_id')
        result = super(AccountBankStatement, self).unlink()
        transfers.unlink()
        return result


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    mollie_json_info = fields.Char()
    mollie_transaction_id = fields.Char()

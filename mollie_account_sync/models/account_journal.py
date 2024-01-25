# -*- coding: utf-8 -*-

import json
import logging
import requests
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)

TIMEOUT = 60
API_DEBUG = False


class AccountJournal(models.Model):

    _inherit = "account.journal"

    mollie_api_key = fields.Char(string="Mollie Organisation Access token")
    mollie_test = fields.Boolean()
    mollie_last_sync = fields.Datetime()

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
            self._mollie_create_bank_statements(payment_data, refund_data, settlement)

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
            capture_data = self._api_get_settlement_captures(settlement['id'])
            chargeback_data = self._api_get_settlement_chargebacks(settlement['id'])
            self._mollie_create_bank_statements(payment_data, refund_data, capture_data, chargeback_data, settlement)

    def _mollie_create_bank_statements(self, payment_data, refund_data, capture_data, chargeback_data, settlement_data, return_lines=False):
        """ Create new bank statement based on settlement, settlement payments and settlement refunds.

            This method also try to guess the partner for statement.

            :param payment_data: list of payments data for given settlement.
            :param refund_data: list of refund data for given settlement.
            :param settlement_data: settlement information.
        """
        BankStatement = self.env['account.bank.statement']
        statement_lines = []

        for payment in payment_data:
            if not payment.get('settlementAmount') or payment.get('status') == 'failed':
                continue
            statement_line = {
                'date': self._format_mollie_date(payment['createdAt']),
                'payment_ref': self._generate_payment_ref(payment['metadata']) or payment['description'],
                'amount': float(payment['settlementAmount']['value']),
                'mollie_transaction_id': payment['id'],
                'journal_id': self.id,
            }
            statement_line.update(self._parse_payment_metadata(payment, 'Payment'))
            statement_lines.append((0, 0, statement_line))

        for refund in refund_data:
            if not refund.get('settlementAmount') or refund.get('status') == 'failed':
                continue
            statement_line = {
                'date': self._format_mollie_date(refund['createdAt']),
                'payment_ref': self._generate_payment_ref(refund.get('metadata')) or refund.get('description') or ('Refund for %s' % refund['id']),
                'amount': float(refund['settlementAmount']['value']),
                'mollie_transaction_id': refund['id'],
                'journal_id': self.id,
            }
            if refund.get('_embedded') and refund['_embedded'].get('payment'):
                statement_line.update(self._parse_payment_metadata(refund['_embedded']['payment'], 'Refund'))
            statement_lines.append((0, 0, statement_line))
        for fee_line in self.get_payment_fees_lines(settlement_data)['lines']:
            statement_lines.append((0, 0, fee_line))

        for capture in capture_data:
            if not capture.get('settlementAmount') or capture.get('status') == 'failed':
                continue
            statement_line = {
                'date': self._format_mollie_date(capture['createdAt']),
                'payment_ref': capture.get('description') or "Klarna capture for Payment Ref: %s" % capture.get('paymentId'),
                'amount': float(capture['settlementAmount']['value']),
                'mollie_transaction_id': capture['id'],
                'journal_id': self.id,
            }
            if capture.get('_embedded') and capture['_embedded'].get('payment'):
                statement_line.update(self._parse_payment_metadata(capture['_embedded']['payment'], 'Capture'))
            statement_lines.append((0, 0, statement_line))

        for chargeback in chargeback_data:
            if not chargeback.get('settlementAmount') or chargeback.get('status') == 'failed':
                continue
            statement_line = {
                'date': self._format_mollie_date(chargeback['createdAt']),
                'payment_ref': chargeback.get('description') or "Chargeback for Payment Ref: %s" % chargeback.get('paymentId'),
                'amount': float(chargeback['settlementAmount']['value']),
                'mollie_transaction_id': chargeback['id'],
                'journal_id': self.id,
            }
            if chargeback.get('_embedded') and chargeback['_embedded'].get('payment'):
                statement_line.update(self._parse_payment_metadata(chargeback['_embedded']['payment'], 'Chargeback'))
            statement_lines.append((0, 0, statement_line))

        # Add full statement amount as minus so statement difference is 0
        # and end user will need to internal transfer same account
        statement_lines.append((0, 0, {
            'date': self._format_mollie_date(settlement_data['createdAt']),
            'payment_ref': 'MOLLIE PAYMENTS REF %s (for Internal Transfer)' % (settlement_data['reference']),
            'amount': - float(settlement_data['amount']['value']),
            'journal_id': self.id,
        }))
        statement_vals = {
            'name': settlement_data['reference'],
            'date': self._format_mollie_date(settlement_data['createdAt']),
            'line_ids': statement_lines,
            'mollie_settlement_id': settlement_data['id'],
            'journal_id': self.id,
        }
        statement = BankStatement.create(statement_vals)
        statement.balance_end_real = statement.balance_end

        # This FIXes Rounding issues
        diff = statement.balance_start - statement.balance_end_real
        if diff >= -0.05 and diff <= 0.05 and diff != 0:
            line_data = [(4, l.id, 0) for l in statement.line_ids]
            last_line = statement.line_ids[-1]
            line_data.append((0, 0, {
                'date': last_line.date,
                'payment_ref': 'Mollie rounding difference',
                'ref': 'Mollie rounding difference',
                'amount': diff
            }))
            statement.line_ids = line_data
            statement.balance_end_real = statement.balance_end

    # =================
    # API CALLS METHODS
    # =================

    def _api_get_settlements(self, limit=None):
        """ Fetch settlements data from mollie api"""
        api_endpoint = "https://api.mollie.com/v2/settlements"
        if limit:
            api_endpoint += '?limit=' + str(limit)
        return self._mollie_api_call(api_endpoint)

    # TODO: settlement payments, refund, capture, and chargeback can merged in one method
    # Fetch data for settlement payment
    def _api_get_settlement_payments(self, settlement_id):
        """ Fetch settlements data from mollie api"""
        api_endpoint = "https://api.mollie.com/v2/settlements/%s/payments?limit=250" % settlement_id
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

    # Fetch data for settlement refund
    def _api_get_settlement_refunds(self, settlement_id):
        """ Fetch settlements data from mollie api"""
        api_endpoint = "https://api.mollie.com/v2/settlements/%s/refunds?embed=payment&limit=250" % settlement_id
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

    # Fetch data for settlement capture
    def _api_get_settlement_captures(self, settlement_id):
        """ Fetch settlements data from mollie api"""
        api_endpoint = "https://api.mollie.com/v2/settlements/%s/captures?embed=payment" % settlement_id
        capture_data = self._api_call_captures_recursive(api_endpoint)
        return capture_data

    def _api_call_captures_recursive(self, api_endpoint):
        captures = []
        capture_data = self._mollie_api_call(api_endpoint)
        if capture_data and capture_data['count'] > 0:
            captures.extend(capture_data['_embedded']['captures'])
        if capture_data["_links"]['next']:
            next_captures = self._api_call_captures_recursive(capture_data["_links"]['next']['href'])
            captures.extend(next_captures)
        return captures

    # Fetch data for settlement chargeback
    def _api_get_settlement_chargebacks(self, settlement_id):
        """ Fetch settlements data from mollie api"""
        api_endpoint = "https://api.mollie.com/v2/settlements/%s/chargebacks?embed=payment&limit=250" % settlement_id
        capture_data = self._api_call_chargebacks_recursive(api_endpoint)
        return capture_data

    def _api_call_chargebacks_recursive(self, api_endpoint):
        chargebacks = []
        chargeback_data = self._mollie_api_call(api_endpoint)
        if chargeback_data and chargeback_data['count'] > 0:
            chargebacks.extend(chargeback_data['_embedded']['chargebacks'])
        if chargeback_data["_links"]['next']:
            next_chargebacks = self._api_call_chargebacks_recursive(chargeback_data["_links"]['next']['href'])
            chargebacks.extend(next_chargebacks)
        return chargebacks

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
                        'payment_ref': line_name,
                        'journal_id':self.id,
                        'amount': l_round(amount)
                    })
                    total += l_round(amount)
        return {
            'amount': total,
            'lines': lines
        }

    def _parse_payment_metadata(self, payment, tx_type):

        json_info = {}
        mollie_provider = self.env.ref('payment.payment_provider_mollie', raise_if_not_found=False)
        statement_line_data = {}

        if payment.get('metadata'):
            json_info.update(payment['metadata'])
        if payment.get('orderId'):
            json_info['mollie_order_id'] = payment.get('orderId')
        if len(json_info.keys()):
            json_info['MollieType'] = tx_type
            statement_line_data['mollie_json_info'] = json.dumps(json_info)

        domain = [('provider_reference', '=', payment['id'])]
        if mollie_provider:
            domain += [('provider_id', '=', mollie_provider.id)]
        transaction = self.env['payment.transaction'].search(domain, limit=1)
        if transaction and transaction.partner_id:
            statement_line_data['partner_id'] = transaction.partner_id.id

        return statement_line_data


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

# -*- coding: utf-8 -*-

import logging
import requests
from werkzeug import urls

from odoo import fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

LIST_TERMINAL_PAGER_LIMIT = 250


class MolliePaymentsTerminal(models.Model):
    _name = 'mollie.payments.terminal'
    _description = 'Mollie Paymenyts Terminal'

    name = fields.Char()
    terminal_id = fields.Char('Terminal ID')
    profile_id = fields.Char('Profile ID')
    provider_id = fields.Many2one('payment.provider', string='Payment Provider')
    serial_number = fields.Char('Serial Number')
    status = fields.Selection([
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('inactive', 'Inactive')
    ])
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)

    def _sync_mollie_terminals(self, provider):
        existing_terminals = self.search([('provider_id', '=', provider.id)])
        terminals_data = self._api_get_terminals(provider._get_terminal_api_key())
        if not terminals_data:
            return
        for terminal in terminals_data:
            terminal_found = existing_terminals.filtered(lambda x: x.terminal_id == terminal['id'])
            currency = self.env['res.currency'].search([('name', '=', terminal['currency'])])

            if not currency:
                raise ValidationError(_('Currency ') + terminal['currency'] + _(' is not active. Please activate it first.'))

            terminal_data = {
                'name': terminal['description'],
                'terminal_id': terminal['id'],
                'profile_id': terminal['profileId'],
                'serial_number': terminal['serialNumber'],
                'status': terminal['status'],
                'currency_id': currency.id,
                'provider_id': provider.id
            }
            if terminal_found:
                terminal_found.write(terminal_data)
            else:
                self.create(terminal_data)

    # ================
    # API CALLS METHOD
    # ================

    def _api_get_terminals(self, mollie_api_key, params=None):
        """ Fetch terminals data from mollie api """
        result = self._mollie_api_call('/terminals', mollie_api_key=mollie_api_key,method='GET', params={'limit': LIST_TERMINAL_PAGER_LIMIT, **(params or {})})
        terminals_data = []
        if result.get('count') > 0:
            terminals_data = result['_embedded']['terminals']
        if result.get('count') == LIST_TERMINAL_PAGER_LIMIT:  # Only when pager size is reached
            last_terminal = terminals_data.pop()  # Mollie Terminal List API's pager also returns terminal given in 'from' parameter so we pop it to avoid duplicates.
            terminals_data += self._api_get_terminals(mollie_api_key=mollie_api_key, params={'from': last_terminal['id']})
        return terminals_data

    # =====================
    # GENERIC TOOLS METHODS
    # =====================


    def _mollie_generate_querystring(self, params):
        """ Mollie uses dictionaries in querystrings with square brackets like this
        https://api.mollie.com/v2/methods?amount[value]=125.91&amount[currency]=EUR
        :param dict params: parameters which needs to be converted in mollie format
        :return: querystring in mollie's format
        :rtype: string
        """
        if not params:
            return None
        parts = []
        for param, value in sorted(params.items()):
            if not isinstance(value, dict):
                parts.append(urls.url_encode({param: value}))
            else:
                # encode dictionary with square brackets
                for key, sub_value in sorted(value.items()):
                    composed = f"{param}[{key}]"
                    parts.append(urls.url_encode({composed: sub_value}))
        if parts:
            return "&".join(parts)


    def _mollie_api_call(self, endpoint, mollie_api_key, data=None, params=None, method='POST', silent=False):
        headers = {
            'content-type': 'application/json',
            "Authorization": f'Bearer {mollie_api_key}',
        }

        endpoint = f'/v2/{endpoint.strip("/")}'
        url = urls.url_join('https://api.mollie.com/', endpoint)
        querystring_params = self._mollie_generate_querystring(params)

        _logger.info('Mollie Sale Terminal CALL on: %s', url)

        try:
            response = requests.request(method, url, params=querystring_params, json=data, headers=headers, timeout=60)
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            error_details = response.json()
            _logger.exception("MOLLIE-SALE-ERROR \n %s", error_details)
            if silent:
                return error_details
            else:
                raise ValidationError("MOLLIE: \n %s" % error_details)
        except requests.exceptions.RequestException as e:
            _logger.exception("unable to communicate with Mollie: %s \n %s", url, e)
            if silent:
                return {'error': "Some thing went wrong"}
            else:
                raise ValidationError("Mollie: " + _("Some thing went wrong."))
        return response.json()

    # =====================
    # ACTIONS METHODS
    # =====================

    def show_form_and_tree(self):
        action = self.env['ir.actions.actions']._for_xml_id('payment.action_payment_transaction')
        action.update({
            'domain': [('terminal_id', '=', self.id)],
        })
        return action

    def action_sync_terminal(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sync Mollie Terminals'),
            'res_model': 'sync.mollie.payments.terminal',
            'views': [[False, 'form']],
            'target': 'new',
            'context': self.env.context
        }

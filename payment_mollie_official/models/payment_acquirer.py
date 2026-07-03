# -*- coding: utf-8 -*-

import logging
import psycopg2
from werkzeug import urls

from odoo import fields, models, service, api, SUPERUSER_ID
from odoo.modules.registry import Registry


_logger = logging.getLogger(__name__)


class PaymentProviderMollie(models.Model):
    _inherit = 'payment.provider'

    # removed required_if_provider becasue we do not want to add production key during testing
    mollie_api_key = fields.Char(string="Mollie API Key", required_if_provider=False, help="The Test or Live API Key depending on the configuration of the provider", groups="base.group_system")
    mollie_api_key_test = fields.Char(string="Test API key", groups="base.group_system")
    mollie_profile_id = fields.Char("Mollie Profile ID", groups="base.group_system")

    mollie_use_components = fields.Boolean(string='Mollie Components', default=True)
    mollie_debug_logging = fields.Boolean('Debug logging', help="Log requests in order to ease debugging")

    # TODO: Deprecated field, not used anywhere, removed in future
    mollie_auto_capture = fields.Boolean('Auto Capture')
    mollie_set_delivery_line_qty = fields.Boolean('Set Delivery Line Qty')
    mollie_automation_action_id = fields.Many2one('base.automation', string='Automation Action')
    mollie_rounding_adjustment = fields.Boolean(string="Rounding Adjustment")
    rounding_line_description = fields.Char(string="Rounding Line Description", translate=True)

    def toggle_mollie_debug(self):
        for provider in self:
            provider.mollie_debug_logging = not provider.mollie_debug_logging

    def _log_logging(self, env, message, function_name, path, provider_id):
        if self.mollie_debug_logging:
            self.env.flush_all()
            db_name = self._cr.dbname
            try:
                with Registry(db_name).cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    IrLogging = env['ir.logging']
                    IrLogging.sudo().create({
                        'name': 'Mollie Payments',
                        'type': 'server',
                        'level': 'DEBUG',
                        'dbname': db_name,
                        'message': message or 'N/A',
                        'func': function_name or 'N/A',
                        'path': path,
                        'line': provider_id,
                    })
            except psycopg2.Error:
                pass

    # ----------------
    # PAYMENT FEATURES
    # ----------------

    def _compute_feature_support_fields(self):
        """ Override of `payment` to enable additional features. """
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'mollie').update({
            'support_refund': 'partial',
            'support_manual_capture': 'partial',
            'support_tokenization': True,
        })

    # --------------
    # ACTION METHODS
    # --------------

    def action_sync_mollie(self):
        """ This method will sync mollie methods and translations via API """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sync Mollie Payment Methods',
            'res_model': 'mollie.sync.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_provider_id': self.id,
            }
        }

    # -----------
    # API methods
    # -----------

    def _api_mollie_get_active_payment_methods(self, extra_params=None, all_methods=None):
        """ Get method data from the mollie. It will return the methods
        that are enabled in the Mollie.
        :param dict extra_params: Optional parameters which are passed to mollie during API call
        :return: details of enabled methods
        :rtype: dict
        """
        result = {}
        extra_params = extra_params or {}
        endpoint = '/methods/all' if all_methods else '/methods'
        params = {'include': 'issuers', **extra_params}

        # get payment api methods
        payemnt_api_methods = self._send_api_request('GET', endpoint, params=params)
        if payemnt_api_methods and payemnt_api_methods.get('count'):
            for method in payemnt_api_methods['_embedded']['methods']:
                result[method['id']] = method
        return result

    def _api_mollie_get_payment_data(self, transaction_reference, force_payment=False):
        """ Fetch the payment records based `transaction_reference`. It is used
        to varify transaction's state after the payment.
        :param str transaction_reference: transaction reference
        :return: details of payment record
        :rtype: dict
        """
        mollie_data = {}

        # Order API deprecated remove the order support in future version
        if transaction_reference.startswith('ord_'):
            mollie_data = self._send_api_request('GET', f'/orders/{transaction_reference}', params={'embed': 'payments'})
        if transaction_reference.startswith('tr_'):    # This is not used
            mollie_data = self._send_api_request('GET', f'/payments/{transaction_reference}')
        if not force_payment:
            return mollie_data

        if mollie_data['resource'] == 'order':
            payments = mollie_data.get('_embedded', {}).get('payments', [])
            if payments:
                # No need to handle multiple payment for same order as we create new order for each failed transaction
                payment_id = payments[0]['id']
                mollie_data = self._send_api_request('GET', f'/payments/{payment_id}')
        return mollie_data

    def _api_mollie_create_customer_id(self):
        """ Create the customer id for currunt user inside the mollie.
        :return: customer id
        :rtype: cuatomer_data
        """
        sudo_user = self.env.user.sudo()
        customer_data = {'name': sudo_user.name, 'metadata': {'odoo_user_id': self.env.user.id}}
        if sudo_user.email:
            customer_data['email'] = sudo_user.email
        return self._send_api_request('POST', '/customers', json=customer_data)

    def _api_mollie_refund(self, amount, currency, payment_reference):
        """ Create the customer id for currunt user inside the mollie.
        :param str amount: amount to refund
        :param str currency: refund curruncy
        :param str payment_reference: transaction reference for refund
        :return: details of payment record
        :rtype: dict
        """
        refund_data = {'amount': {'value': "%.2f" % amount, 'currency': currency}}
        return self._send_api_request('POST', f'/payments/{payment_reference}/refunds', json=refund_data)

    def _api_mollie_refund_data(self, payment_reference, refund_reference):
        """ Get data for the refund from mollie.
        :param str refund_reference: refund record reference
        :param str payment_reference: refund payment reference
        :return: details of refund record
        :rtype: dict
        """
        return self._send_api_request('GET', f'/payments/{payment_reference}/refunds/{refund_reference}')

    def _api_get_customer_data(self, customer_id):
        """ Create the customer id for currunt user inside the mollie.
        :param str customer_id: customer_id in mollie
        :rtype: dict
        """
        return self._send_api_request('GET', f'/customers/{customer_id}')

    def _api_mollie_get_capture_data(self, payment_reference):
        """ Fetch capture records based `payment_reference`. It is used
        to verify child transaction's state after capture the payment.
        :param str payment_reference: payment reference
        :return: details of capture records
        :rtype: dict
        """
        return self._send_api_request('GET', f'/payments/{payment_reference}/captures')

    def _api_mollie_sync_capture(self, order_reference, capture_data):
        """ Capture amount from mollie
        :param str order_reference: order record reference
        :param dict capture_data: captured amount data

        """
        return self._send_api_request('POST', f'/payments/{order_reference}/captures', json=capture_data)

    def _api_mollie_void_remaining_payment(self, order_reference):
        """ Void remaining amount from mollie
        :param str order_reference: order record reference

        """
        return self._send_api_request('POST', f'/payments/{order_reference}/release-authorization')

    # -------------------------
    # Helper methods for mollie
    # -------------------------

    def _send_api_request(
        self, method, endpoint, *, params=None, data=None, json=None, reference=None, **kwargs
    ):
        """ Inherited method to populate query strings. """
        if self.code == 'mollie' and params:
            params = self._mollie_generate_querystring(params)
        return super()._send_api_request(method, endpoint, params=params, data=data, json=json, reference=reference, **kwargs)

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

    def _get_all_mollie_methods_codes(self):
        """ Return list of method codes for mollie.
        :return: list of method codes
        :rtype: list
        """
        return self.search([('code', '=', 'mollie')]).with_context(active_test=False).mapped('payment_method_ids.code')

    def _mollie_get_customer_id(self, partner):
        """ Get or create a Mollie customer ID for the given partner.

        Checks existing payment.token records from Mollie for the partner to
        retrieve a customer ID. Validates it via API and creates a new one if
        no valid ID is found.

        :param recordset partner: res.partner record
        :return: Mollie customer ID or False
        :rtype: str or False
        """
        self.ensure_one()
        existing_token = self.env['payment.token'].sudo().search([
            ('partner_id', '=', partner.id),
            ('provider_id', '=', self.id),
            ('company_id', '=', self.company_id.id),
            ('mollie_customer_id', '!=', False),
        ], limit=1, order='create_date desc')

        if existing_token and self._mollie_validate_customer_id(existing_token.mollie_customer_id):
            return existing_token.mollie_customer_id

        customer_data = self._api_mollie_create_customer_id()
        if customer_data and customer_data.get('id'):
            return customer_data['id']
        return False

    def _mollie_validate_customer_id(self, customer_id):
        """ Validate a Mollie customer ID via API.

        :param str customer_id: Mollie customer ID to validate
        :return: True if valid, False if deleted/invalid
        :rtype: bool
        """
        self.ensure_one()
        customer_data = self._api_get_customer_data(customer_id)
        if not customer_data or customer_data.get('status'):
            return False
        return True

    # === REQUEST HELPERS === #

    def _build_request_headers(self, *args, **kwargs):
        """ Inherited the request header to populate mollie api key. """
        headers = super()._build_request_headers(*args, **kwargs)
        if self.code != 'mollie':
            return headers

        if self.state == 'test':
            headers['Authorization'] = f'Bearer {self.mollie_api_key_test}'

        # User agent strings used by mollie to find issues in integration
        odoo_version = service.common.exp_version()['server_version']
        mollie_extended_app_version = self.env.ref('base.module_payment_mollie_official').installed_version
        headers['User-Agent'] = f'Odoo/{odoo_version} MollieOdoo/{mollie_extended_app_version}'
        return headers

    def _parse_response_content(self, response, **kwargs):
        """Override of `payment` to parse the response content."""
        if self.code == 'mollie' and response.status_code in [202, 204]:
            return True
        return super()._parse_response_content(response, **kwargs)
# -*- coding: utf-8 -*-

import json
import logging
import psycopg2
import requests
from werkzeug import urls

from odoo import _, fields, models, service, api, SUPERUSER_ID, Command
from odoo.exceptions import ValidationError
from odoo.modules.registry import Registry


_logger = logging.getLogger(__name__)


class PaymentProviderMollie(models.Model):
    _inherit = 'payment.provider'

    # removed required_if_provider becasue we do not want to add production key during testing
    mollie_api_key = fields.Char(string="Mollie API Key", required_if_provider=False, help="The Test or Live API Key depending on the configuration of the provider", groups="base.group_system")
    mollie_api_key_test = fields.Char(string="Test API key", groups="base.group_user")
    mollie_profile_id = fields.Char("Mollie Profile ID", groups="base.group_user")

    mollie_use_components = fields.Boolean(string='Mollie Components', default=True)
    mollie_show_save_card = fields.Boolean(string='Single-Click payments')
    mollie_debug_logging = fields.Boolean('Debug logging', help="Log requests in order to ease debugging")

    # TODO: Deprecated field, not used anywhere, removed in future
    mollie_auto_capture = fields.Boolean('Auto Capture')
    mollie_set_delivery_line_qty = fields.Boolean('Set Delivery Line Qty')
    mollie_automation_action_id = fields.Many2one('base.automation', string='Automation Action')

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
        })

    # --------------
    # ACTION METHODS
    # --------------

    def action_sync_mollie(self):
        """ This method will sync mollie methods and translations via API """
        self.ensure_one()
        self.env['payment.method']._sync_mollie_methods(self)

    # -----------
    # API methods
    # -----------

    def _mollie_make_request(self, endpoint, params=None, data=None, method='POST', silent_errors=False):
        """
        Overridden method to manage 'params' rest of the things works as it is.

        We are not using super as we want diffrent User-Agent for all requests.
        We also want to use separate test api key in test mode.

        Note: self.ensure_one()
        :param str endpoint: The endpoint to be reached by the request
        :param dict params: The querystring of the request
        :param dict data: The payload of the request
        :param str method: The HTTP method of the request
        :return The JSON-formatted content of the response
        :rtype: dict
        :raise: ValidationError if an HTTP error occurs
        """
        self.ensure_one()

        endpoint = f'/v2/{endpoint.strip("/")}'
        url = urls.url_join('https://api.mollie.com/', endpoint)
        querystring_params = self._mollie_generate_querystring(params)

        # User agent strings used by mollie to find issues in integration
        odoo_version = service.common.exp_version()['server_version']
        mollie_extended_app_version = self.env.ref('base.module_payment_mollie_official').installed_version
        mollie_api_key = self.mollie_api_key_test if self.state == 'test' else self.mollie_api_key

        headers = {
            "Accept": "application/json",
            "Authorization": f'Bearer {mollie_api_key}',
            "Content-Type": "application/json",
            "User-Agent": f'Odoo/{odoo_version} MollieOdoo/{mollie_extended_app_version}',
        }

        error_msg, result, status_code = _("Could not establish the connection to the API."), False, None
        json_data = None
        if data:
            json_data = json.dumps(data)

        try:
            response = requests.request(method, url, params=querystring_params, data=json_data, headers=headers, timeout=60)
            if response.status_code in [204, 202]:
                return True  # returned no content
            result = response.json()
            if response.status_code not in [200, 201]:  # doc reference https://docs.mollie.com/overview/handling-errors
                error_msg = f"Error[{response.status_code}]: {result.get('title')} - {result.get('detail')}"
                status_code = response.status_code
                _logger.exception("Error from mollie: %s", result)
            response.raise_for_status()
        except requests.exceptions.RequestException:
            if silent_errors:
                result = {'error': error_msg, 'status_code': status_code}
            else:
                raise ValidationError("Mollie: " + error_msg)
        finally:
            if self.mollie_debug_logging:
                message = str(json.dumps({
                    'PARAMS': params,
                    'DATA': data,
                    'RESPONSE': result,
                }, indent=4))
                self._log_logging(self.env, message, method, url, self.id)
        return result

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
        payemnt_api_methods = self._mollie_make_request(endpoint, params=params, method="GET", silent_errors=True)
        if payemnt_api_methods and payemnt_api_methods.get('count'):
            for method in payemnt_api_methods['_embedded']['methods']:
                result[method['id']] = method
        return result

    def _api_mollie_create_payment_record(self, payment_data, params=None, silent_errors=False):
        """ Create the payment records on the mollie. It calls payment or order
        API based on 'api_type' param.
        :param str api_type: api is selected based on this parameter
        :param dict payment_data: payment data
        :return: details of created payment record
        :rtype: dict
        """
        return self._mollie_make_request('/payments', data=payment_data, params=params, method="POST", silent_errors=silent_errors)

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
            mollie_data = self._mollie_make_request(f'/orders/{transaction_reference}', params={'embed': 'payments'}, method="GET")
        if transaction_reference.startswith('tr_'):    # This is not used
            mollie_data = self._mollie_make_request(f'/payments/{transaction_reference}', method="GET")
        if not force_payment:
            return mollie_data

        if mollie_data['resource'] == 'order':
            payments = mollie_data.get('_embedded', {}).get('payments', [])
            if payments:
                # No need to handle multiple payment for same order as we create new order for each failed transaction
                payment_id = payments[0]['id']
                mollie_data = self._mollie_make_request(f'/payments/{payment_id}', method="GET")
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
        return self._mollie_make_request('/customers', data=customer_data, method="POST")

    def _api_mollie_refund(self, amount, currency, payment_reference):
        """ Create the customer id for currunt user inside the mollie.
        :param str amount: amount to refund
        :param str currency: refund curruncy
        :param str payment_reference: transaction reference for refund
        :return: details of payment record
        :rtype: dict
        """
        refund_data = {'amount': {'value': "%.2f" % amount, 'currency': currency}}
        return self._mollie_make_request(f'/payments/{payment_reference}/refunds', data=refund_data, method="POST")

    def _api_mollie_refund_data(self, payment_reference, refund_reference):
        """ Get data for the refund from mollie.
        :param str refund_reference: refund record reference
        :param str payment_reference: refund payment reference
        :return: details of refund record
        :rtype: dict
        """
        return self._mollie_make_request(f'/payments/{payment_reference}/refunds/{refund_reference}', method="GET")

    def _api_get_customer_data(self, customer_id, silent_errors=False):
        """ Create the customer id for currunt user inside the mollie.
        :param str customer_id: customer_id in mollie
        :rtype: dict
        """
        return self._mollie_make_request(f'/customers/{customer_id}', method="GET", silent_errors=silent_errors)

    def _api_mollie_get_capture_data(self, payment_reference):
        """ Fetch capture records based `payment_reference`. It is used
        to verify child transaction's state after capture the payment.
        :param str payment_reference: payment reference
        :return: details of capture records
        :rtype: dict
        """
        return self._mollie_make_request(f'/payments/{payment_reference}/captures', method="GET")

    def _api_mollie_sync_capture(self, order_reference, capture_data):
        """ Capture amount from mollie
        :param str order_reference: order record reference
        :param dict capture_data: captured amount data

        """
        return self._mollie_make_request(f'/payments/{order_reference}/captures', data=capture_data, method="POST")

    def _api_mollie_void_remaining_payment(self, order_reference):
        """ Void remaining amount from mollie
        :param str order_reference: order record reference

        """
        return self._mollie_make_request(f'/payments/{order_reference}/release-authorization', method="POST")

    # -------------------------
    # Helper methods for mollie
    # -------------------------

    def _mollie_user_locale(self):
        user_lang = self.env.context.get('lang')
        supported_locale = self._mollie_get_supported_locale()
        return user_lang if user_lang in supported_locale else 'en_US'

    def _mollie_get_supported_locale(self):
        return [
            'en_US', 'nl_NL', 'nl_BE', 'fr_FR',
            'fr_BE', 'de_DE', 'de_AT', 'de_CH',
            'es_ES', 'ca_ES', 'pt_PT', 'it_IT',
            'nb_NO', 'sv_SE', 'fi_FI', 'da_DK',
            'is_IS', 'hu_HU', 'pl_PL', 'lv_LV',
            'lt_LT', 'en_GB']

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

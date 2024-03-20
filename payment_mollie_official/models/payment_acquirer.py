# -*- coding: utf-8 -*-

import json
import base64
import logging
import requests
from werkzeug import urls

from odoo import _, fields, models, service
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)


class PaymentProviderMollie(models.Model):
    _inherit = 'payment.provider'

    # removed required_if_provider becasue we do not want to add production key during testing
    mollie_api_key = fields.Char(string="Mollie API Key", required_if_provider=False, help="The Test or Live API Key depending on the configuration of the provider", groups="base.group_system")
    mollie_api_key_test = fields.Char(string="Test API key", groups="base.group_user")
    mollie_profile_id = fields.Char("Mollie Profile ID", groups="base.group_user")

    mollie_use_components = fields.Boolean(string='Mollie Components', default=True)
    mollie_show_save_card = fields.Boolean(string='Single-Click payments')

    # ----------------
    # PAYMENT FEATURES
    # ----------------

    def _compute_feature_support_fields(self):
        """ Override of `payment` to enable additional features. """
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'mollie').update({
            'support_refund': 'partial',
            'support_manual_capture': 'partial'
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
        params = self._mollie_generate_querystring(params)

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

        error_msg, result = _("Could not establish the connection to the API."), False
        if data:
            data = json.dumps(data)

        try:
            response = requests.request(method, url, params=params, data=data, headers=headers, timeout=60)
            if response.status_code == 204:
                return True  # returned no content
            result = response.json()
            if response.status_code not in [200, 201]:  # doc reference https://docs.mollie.com/overview/handling-errors
                error_msg = f"Error[{response.status_code}]: {result.get('title')} - {result.get('detail')}"
                _logger.exception("Error from mollie: %s", result)
            response.raise_for_status()
        except requests.exceptions.RequestException:
            if silent_errors:
                return response.json()
            else:
                raise ValidationError("Mollie: " + error_msg)
        return result

    def _api_mollie_get_active_payment_methods(self, extra_params=None):
        """ Get method data from the mollie. It will return the methods
        that are enabled in the Mollie.
        :param dict extra_params: Optional parameters which are passed to mollie during API call
        :return: details of enabled methods
        :rtype: dict
        """
        result = {}
        extra_params = extra_params or {}
        params = {'include': 'issuers', 'includeWallets': 'applepay', **extra_params}

        # get payment api methods
        payemnt_api_methods = self._mollie_make_request('/methods', params=params, method="GET", silent_errors=True)
        if payemnt_api_methods and payemnt_api_methods.get('count'):
            for method in payemnt_api_methods['_embedded']['methods']:
                method['support_payment_api'] = True
                result[method['id']] = method

        # get order api methods
        params['resource'] = 'orders'
        order_api_methods = self._mollie_make_request('/methods', params=params, method="GET", silent_errors=True)
        if order_api_methods and order_api_methods.get('count'):
            for method in order_api_methods['_embedded']['methods']:
                if method['id'] in result:
                    result[method['id']]['support_order_api'] = True
                else:
                    method['support_order_api'] = True
                    result[method['id']] = method
        return result or {}

    def _api_mollie_create_payment_record(self, api_type, payment_data, params=None, silent_errors=False):
        """ Create the payment records on the mollie. It calls payment or order
        API based on 'api_type' param.
        :param str api_type: api is selected based on this parameter
        :param dict payment_data: payment data
        :return: details of created payment record
        :rtype: dict
        """
        endpoint = '/orders' if api_type == 'order' else '/payments'
        return self._mollie_make_request(endpoint, data=payment_data, params=params, method="POST", silent_errors=silent_errors)

    def _api_mollie_get_payment_data(self, transaction_reference, force_payment=False):
        """ Fetch the payment records based `transaction_reference`. It is used
        to varify transaction's state after the payment.
        :param str transaction_reference: transaction reference
        :return: details of payment record
        :rtype: dict
        """
        mollie_data = {}
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
        data = self._mollie_make_request(f'/payments/{payment_reference}/refunds', data=refund_data, method="POST")
        return data

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

    def _mollie_fetch_image_by_url(self, image_url):
        image_base64 = False
        try:
            image_base64 = base64.b64encode(requests.get(image_url).content)
        except Exception:
            _logger.warning('Can not import mollie image %s', image_url)
        return image_base64

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

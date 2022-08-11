# -*- coding: utf-'8' "-*-"

import json
import logging
import pprint
import requests

from odoo import models, fields, api
from odoo.tools.float_utils import float_compare
from odoo.tools.translate import _
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class AcquirerMollie(models.Model):
    _inherit = 'payment.acquirer'
    # Fields

    provider = fields.Selection(selection_add=[('mollie', 'Mollie')])
    mollie_api_key_test = fields.Char('Mollie Test API key', size=40, required_if_provider='mollie', groups='base.group_user')
    mollie_api_key_prod = fields.Char('Mollie Live API key', size=40, required_if_provider='mollie', groups='base.group_user')

    @api.onchange('mollie_api_key_test')
    def _onchange_mollie_api_key_test(self):
        if self.mollie_api_key_test:
            if not self.mollie_api_key_test[:5] == 'test_':
                return {'warning': {'title': "Warning", 'message': "Value of Test API Key is not valid. Should begin with 'test_'",}}

    @api.onchange('mollie_api_key_prod')
    def _onchange_mollie_api_key_prod(self):
        if self.mollie_api_key_prod:
            if not self.mollie_api_key_prod[:5] == 'live_':
                return {'warning': {'title': "Warning", 'message': "Value of Live API Key is not valid. Should begin with 'live_'",}}

    def _get_mollie_api_keys(self, environment):
        keys = {'prod': self.mollie_api_key_prod,
                'test': self.mollie_api_key_test
                }
        return {'mollie_api_key': keys.get(environment, keys['test']), }

    def _get_mollie_urls(self, environment):
        """ Mollie URLS """
        url = {
            'prod': 'https://api.mollie.nl/v1/',
            'test': 'https://api.mollie.nl/v1/', }

        return {'mollie_form_url': url.get(environment, url['test']), }

    @api.multi
    def mollie_form_generate_values(self, values):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        currency = self.env['res.currency'].sudo().browse(values['currency_id'])
        language =  values.get('partner_lang')
        name = values.get('partner_name')
        email = values.get('partner_email')
        zip = values.get('partner_zip')
        address = values.get('partner_address')
        town = values.get('partner_city')
        country = values.get('partner_country') and values.get('partner_country').code or ''
        phone = values.get('partner_phone')

        amount = values['amount']
        mollie_key = getattr(self, 'id')

        mollie_tx_values = dict(values)
        mollie_tx_values.update({
            'OrderId': values['reference'],
            'Description': values['reference'],
            'Currency': currency.name,
            'Amount': amount,
            'Key': mollie_key, #self._get_mollie_api_keys(self.environment)['mollie_api_key'],
            'URL' : self._get_mollie_urls(self.environment)['mollie_form_url'],
            'BaseUrl': base_url,
            'Language': language,
            'Name': name,
            'Email': email,
            'Zip': zip,
            'Address': address,
            'Town': town,
            'Country': country,
            'Phone': phone
        })

        return mollie_tx_values

    @api.multi
    def mollie_get_form_action_url(self):
        self.ensure_one()
        return "/payment/mollie/intermediate"


class TxMollie(models.Model):
    _inherit = 'payment.transaction'

    @api.multi
    def _mollie_form_get_tx_from_data(self, data):
        reference = data.get('reference')
        payment_tx = self.search([('reference', '=', reference)])

        if not payment_tx or len(payment_tx) > 1:
            error_msg = _('received data for reference %s') % (pprint.pformat(reference))
            if not payment_tx:
                error_msg += _('; no order found')
            else:
                error_msg += _('; multiple order found')
            _logger.info(error_msg)
            raise ValidationError(error_msg)

        return payment_tx

    @api.multi
    def _mollie_form_get_invalid_parameters(self, data):
        invalid_parameters = []

        return invalid_parameters

    @api.multi
    def _mollie_form_validate(self, data):
        """
        Check transaction status on Mollie's API and
        set to done in Odoo if paid.
        """
        reference = data.get('reference')

        acquirer = self.acquirer_id

        tx = self._mollie_form_get_tx_from_data(data)

        transactionId = tx.acquirer_reference

        _logger.info('Validated transfer payment for tx %s: set as pending' % (reference))
        mollie_api_key = acquirer._get_mollie_api_keys(acquirer.environment)['mollie_api_key']
        url_base = acquirer._get_mollie_urls(acquirer.environment)['mollie_form_url']

        url_base = url_base.rstrip("/")
        url = "{base}/payments/{transaction_id}".format(
            base=url_base, transaction_id=transactionId
        )

        if acquirer.environment == 'test':
            payload = {"testmode": True}
        else:
            payload = {}

        headers = {'content-type': 'application/json', 'Authorization': 'Bearer ' + mollie_api_key}

        _logger.info("GET ", url)
        mollie_response = requests.get(
            url, params=payload, headers=headers).json()

        response_id = mollie_response.get("id")
        if response_id != transactionId:
            _logger.error('Mollie: response transaction id does not match.')
            return True

        if self.state == 'done':
            _logger.info('Mollie: trying to validate an already validated tx (ref %s)', reference)
            return True

        status = mollie_response.get("status", "undefined")

        if status == "paid":
            paid_datetime = mollie_response["paidDatetime"].replace(".0Z", "")
            date_validate = fields.datetime.strptime(paid_datetime, "%Y-%m-%dT%H:%M:%S")
            vals = {
                'state': 'done',
                'date_validate':  date_validate,
                'acquirer_reference': transactionId,
            }

            self.write(vals)

            return True
        elif status in ["cancelled", "expired", "failed"]:
            self.write({
                'state': 'cancel',
                'acquirer_reference': transactionId,
            })
            return False
        elif status in ["open", "pending"]:
            self.write({
                'state': 'pending',
                'acquirer_reference': transactionId,
            })
            return False
        else:
            self.write({
                'state': 'error',
                'acquirer_reference': transactionId,
            })
            return False

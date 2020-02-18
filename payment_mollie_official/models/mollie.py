# -*- coding: utf-8 -*-
# #############################################################################
#
#    Copyright Mollie (C) 2019
#    Contributor: Eezee-It <info@eezee-it.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################

import base64
import logging
import pprint

import dateutil.parser
from mollie.api.client import Client
import pytz
import requests

from odoo import models, fields, api
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.http import request
from odoo.tools.translate import _

_logger = logging.getLogger(__name__)

# minimum and maximum amounts per payment method
DEFAULT_METHOD_VALUES = {
    'ideal': (0.01, 50000.00),
    'bancontact': (0.02, 50000.00),
    'belfius': (0.01, 50000.00),
    'kbc': (0.01, 50000.00),
    'inghomepay': (0.01, 50000.00),
    'creditcard': (0.01, 2000.00),
    'sofort': (0.01, 5000.00),
    'giropay': (1.0, 50000.00),
    'eps': (1.0, 10000.00),
    'banktransfer': (0.01, 1000.00),
    'paypal': (0.01, 8000.00),
    'bitcoin': (1, 15000.00),
    'klarnapaylater': (0.01, 2000.00),
    'klarnasliceit': (0.01, 2000.00),
    'paysafecard': (1, 999.00),
}


def get_as_base64(url):
    return base64.b64encode(requests.get(url).content)


def get_base_url(env):
    base_url = env['ir.config_parameter'].sudo().get_param('web.base.url')
    return base_url


def get_mollie_provider(env):
    provider = env['payment.acquirer'].sudo()._get_main_mollie_provider()
    return provider


def get_mollie_provider_key(env):
    provider = env['payment.acquirer'].sudo()._get_main_mollie_provider()
    key = provider._get_mollie_api_keys(provider.environment)['mollie_api_key']
    return key


class PaymentIcon(models.Model):
    _inherit = 'payment.icon'
    _order = 'sequence'

    sequence = fields.Integer(
        'Sequence', default=1,
        help='Gives the sequence order when displaying a method list')
    provider = fields.Char(string='Provider')
    acquirer_reference = fields.Char(
        string='Acquirer Reference',
        readonly=True,
        help='Reference of the order as stored in the acquirer database')
    currency_ids = fields.Many2many('res.currency',
                                    string='specific Currencies')
    country_ids = fields.Many2many('res.country',
                                   string='specific Countries')
    name = fields.Char(translate=True)
    minimum_amount = fields.Float('Minimum amount',
                                  default=0.1,
                                  help='the minimum amount per payment method')
    maximum_amount = fields.Float('Maximum amount',
                                  default=50000.0,
                                  help='the maximum amount per payment method')

    @api.onchange('provider', 'acquirer_reference')
    def onchange_provider_ref(self):
        if self.provider == 'mollie' and self.acquirer_reference and\
                DEFAULT_METHOD_VALUES.get(
                self.acquirer_reference, False):
            self.minimum_amount = DEFAULT_METHOD_VALUES[
                self.acquirer_reference][0]
            self.maximum_amount = DEFAULT_METHOD_VALUES[
                self.acquirer_reference][1]
        else:
            self.minimum_amount = 0.01
            self.maximum_amount = 50000.0


class AcquirerMollieMethod(models.Model):
    _name = 'payment.acquirer.method'
    _description = 'Mollie payment acquirer details'
    _order = 'sequence'

    name = fields.Char('Description', index=True,
                       required=True,
                       translate=True)
    sequence = fields.Integer(
        'Sequence', default=1,
        help='Gives the sequence order when displaying a method list')
    acquirer_id = fields.Many2one('payment.acquirer', 'Acquirer')
    acquirer_reference = fields.Char(
        string='Acquirer Reference',
        readonly=True,
        required=True,
        help='Reference of the order as stored in the acquirer database')
    image_small = fields.Binary(
        "Icon", attachment=True,
        help="Small-sized image of the method. It is automatically "
             "resized as a 64x64px image, with aspect ratio preserved. "
             "Use this field anywhere a small image is required.")
    currency_ids = fields.Many2many('res.currency',
                                    string='specific Currencies')
    country_ids = fields.Many2many('res.country',
                                   string='specific Countries')


class AcquirerMollie(models.Model):
    _inherit = 'payment.acquirer'

    _mollie_client = Client()

    provider = fields.Selection(selection_add=[('mollie', 'Mollie')])
    mollie_api_key_test = fields.Char(
        'Mollie Test API key', size=40, required_if_provider='mollie',
        groups='base.group_user')
    mollie_api_key_prod = fields.Char('Mollie Live API key', size=40,
                                      required_if_provider='mollie',
                                      groups='base.group_user')
    dashboard_url = fields.Char(string="Dashboard URL")
    method_ids = fields.One2many('payment.acquirer.method',
                                 'acquirer_id', 'Supported methods')

#     @api.multi
#     @api.constrains('provider')
#     def _check_reconcile(self):
#         for rec in self:
#             if rec.provider == 'mollie':
#                 already_exist = self._get_main_mollie_provider()
#                 if already_exist:
#                     raise ValidationError(
#                         _("Sorry you can not create many Mollie acquirer.\n"
#                             "You can configure the payment methods"
#                             " for the one that already exists"))

    @api.model
    def _get_main_mollie_provider(self):
        return self.sudo().search([('provider', '=', 'mollie')], order="id",
                                  limit=1) or False

    @api.onchange('mollie_api_key_test')
    def _onchange_mollie_api_key_test(self):
        if self.mollie_api_key_test:
            if not self.mollie_api_key_test[:5] == 'test_':
                return {'warning':
                        {'title': "Warning",
                         'message': "Value of Test API Key is not valid."
                         " Should begin with 'test_'", }}

    @api.onchange('mollie_api_key_prod')
    def _onchange_mollie_api_key_prod(self):
        if self.mollie_api_key_prod:
            if not self.mollie_api_key_prod[:5] == 'live_':
                return {
                    'warning': {'title': "Warning",
                                'message': "Value of Live API Key is not "
                                "valid. Should begin with 'live_'", }}

    def _get_mollie_api_keys(self, environment):
        keys = {'prod': self.mollie_api_key_prod,
                'test': self.mollie_api_key_test
                }
        return {'mollie_api_key': keys.get(environment, keys['test']), }

    @api.onchange('method_ids')
    def _onchange_method_ids(self):
        return self.update_payment_icon_ids()

    def _get_mollie_urls(self, environment):
        """ Mollie URLS """
        url = {
            'prod': 'https://api.mollie.com/v2',
            'test': 'https://api.mollie.com/v2', }

        return {'mollie_form_url': url.get(environment, url['test']), }

    @api.multi
    def mollie_form_generate_values(self, values):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo(
        ).get_param('web.base.url')
        mollie_api_key = self._get_mollie_api_keys(
            self.environment)['mollie_api_key']
        mollie_tx_values = dict(values)
        order_id = request.session.get('sale_last_order_id')
        mollie_tx_values.update({
            'OrderName': values.get('reference'),
            'Description': values.get('reference'),
            'Amount': '%.2f' % float(values.get('amount')),
            'Currency': values['currency'] and values['currency'].name or '',
            'Key': mollie_api_key,
            'URL': self._get_mollie_urls(self.environment)['mollie_form_url'],
            'BaseUrl': base_url,
            'Language': values.get('partner_lang'),
            'Name': values.get('partner_name'),
            'Email': values.get('partner_email'),
            'Zip': values.get('partner_zip'),
            'Address': values.get('partner_address'),
            'Town': values.get('partner_city'),
            'Country': values.get('partner_country') and
            values.get('partner_country').code or '',
            'Phone': values.get('partner_phone'),
            'webhookUrl': base_url,
            'OrderId': order_id,
        })
        return mollie_tx_values

    @api.multi
    def mollie_get_form_action_url(self):
        self.ensure_one()
        return "/payment/mollie/intermediate"

    @api.multi
    def update_payment_icon_ids(self):
        self.ensure_one()
        if self.provider != 'mollie':
            return
        icon_model = self.env['payment.icon']
        icon_ids = []
        for method in self.method_ids:
            icon = icon_model.search([
                ('acquirer_reference', 'ilike', method.acquirer_reference)],
                limit=1)
            if not icon:
                icon = icon_model.create({
                    'name': method.name,
                    'acquirer_reference': method.acquirer_reference,
                    'image': method.image_small,
                    'sequence': method.sequence,
                    'provider': self.provider,
                    'currency_ids': method.currency_ids,
                    'country_ids': method.country_ids
                })
                icon.onchange_provider_ref()
            icon_ids.append(icon.id)
            icon.write({'sequence': method.sequence,
                        'provider': self.provider})

        return self.update({'payment_icon_ids': [(6, 0, icon_ids)]})

    @api.multi
    def update_available_mollie_methods(self):
        for acquirer in self:
            if acquirer.provider != 'mollie':
                continue
            mollie_api_key = self._get_mollie_api_keys(
                self.environment)['mollie_api_key']
            acquirer.method_ids.unlink()
            try:
                self._mollie_client.set_api_key(mollie_api_key)
                methods = self._mollie_client.methods.list(resource='orders')
                method_ids = []
                if methods.get('_embedded', False):
                    i = 10
                    for method in methods.get('_embedded',
                                              {"methods": []})["methods"]:
                        image_url = method['image']['size1x']
                        image = get_as_base64(image_url)
                        values = {
                            'name': method['description'],
                            'acquirer_reference': method['id'],
                            'acquirer_id': acquirer.id,
                            'image_small': image,
                            'sequence': i,
                        }
                        method_ids.append((0, _, values))
                        i += 1
                acquirer.write({'method_ids': method_ids})
                acquirer.update_payment_icon_ids()
            except Exception as e:
                _logger.info("__Error!_get_mollie_order__ %s" % (e,))
        return True

    @api.model
    def _cron_update_mollie_methods(self):
        objects = self.search([('provider', '=', 'mollie')])
        return objects.update_available_mollie_methods()

    @api.multi
    def write(self, values):
        res = super(AcquirerMollie, self).write(values)
        if 'mollie_api_key_test' in values or 'mollie_api_key_prod' in values:
            self.update_available_mollie_methods()
        return res


class TxMollie(models.Model):
    _inherit = 'payment.transaction'

    @api.model
    def _mollie_form_get_tx_from_data(self, data):
        reference = data.get('reference')
        payment_tx = self.search([('reference', '=', reference)])

        if not payment_tx or len(payment_tx) > 1:
            error_msg = _('received data for reference %s') % (
                pprint.pformat(reference))
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
        reference = data.get('reference')
        acquirer = self.acquirer_id
        if self.state == 'done':
            _logger.info(
                'Mollie: trying to validate an already validated tx (ref %s)',
                reference)
            return True

        mollie_client = Client()
        tx = self._mollie_form_get_tx_from_data(data)
        transactionId = tx['acquirer_reference']
        _logger.info("Validated transfer payment forTx %s: set as pending" % (
            reference))

        mollie_api_key = acquirer._get_mollie_api_keys(
            acquirer.environment)['mollie_api_key']
        mollie_client.set_api_key(mollie_api_key)
        mollie_response = mollie_client.payments.get(transactionId)
        try:
            # dateutil and pytz don't recognize abbreviations PDT/PST
            tzinfos = {
                'PST': -8 * 3600,
                'PDT': -7 * 3600,
            }
            date = dateutil.parser.parse(data.get('createdAt'),
                                         tzinfos=tzinfos).astimezone(pytz.utc)
        except:
            date = fields.Datetime.now()
        res = {
            'acquirer_reference': mollie_response.get('id', ''),
        }

        status = mollie_response.get("status", "undefined")

        if status in ["paid", "authorized"]:
            res.update(date=date)
            self._set_transaction_done()
            return self.write(res)

        elif status in ["canceled", "expired", "failed"]:
            self._set_transaction_cancel()
            return self.write(res)

        elif status in ["open", "pending"]:
            self._set_transaction_pending()
            return self.write(res)

        else:
            msg = "Error/%s/%s" % (transactionId, reference)
            self._set_transaction_error(msg)
            return self.write(res)

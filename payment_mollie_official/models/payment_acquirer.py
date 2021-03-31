# -*- coding: utf-8 -*-

import base64
import logging
import requests
from werkzeug import urls
from mollie.api.client import Client as MollieClient
from mollie.api.error import UnprocessableEntityError

from odoo import _, api, fields, models, service
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment_mollie_official.controllers.main import MollieController

_logger = logging.getLogger(__name__)


class PaymentAcquirerMollie(models.Model):
    _inherit = 'payment.acquirer'

    provider = fields.Selection(selection_add=[('mollie', 'Mollie')], ondelete={'mollie': 'set default'})
    mollie_api_key_test = fields.Char("Mollie Test API key", required_if_provider="mollie", groups="base.group_user")
    mollie_api_key_prod = fields.Char("Mollie Live API key", required_if_provider="mollie", groups="base.group_user")
    mollie_profile_id = fields.Char("Mollie Profile ID", groups="base.group_user")
    mollie_methods_ids = fields.One2many('mollie.payment.method', 'parent_id', string='Mollie Payment Methods')
    mollie_voucher_ids = fields.One2many('mollie.voucher.line', 'acquirer_id', string='Mollie Voucher Config')
    mollie_voucher_enabled = fields.Boolean(compute="_compute_mollie_voucher_enabled")

    @api.depends('mollie_methods_ids')
    def _compute_mollie_voucher_enabled(self):
        for acquirer in self:
            acquirer.mollie_voucher_enabled = False
            if acquirer.provider == 'mollie':
                if acquirer.mollie_methods_ids.filtered(lambda m: m.method_id_code == 'voucher' and m.active_on_shop):
                    acquirer.mollie_voucher_enabled = True

    def action_mollie_sync_methods(self):
        methods = self._api_mollie_get_active_payment_methods()
        if methods:
            self._sync_mollie_methods(methods)

    def _sync_mollie_methods(self, methods_dict):

        existing_methods = self.with_context(active_test=False).mollie_methods_ids

        for method in existing_methods:
            if method.method_id_code in methods_dict.keys():
                # Update method
                data = methods_dict[method.method_id_code]
                method.write({
                    'min_amount': data['minimumAmount'] and data['minimumAmount']['value'] or 0,
                    'max_amount': data['maximumAmount'] and data['maximumAmount']['value'] or 0,
                    'active': True,
                    'supports_order_api': data.get('support_order_api', False),
                    'supports_payment_api': data.get('support_payment_api', False)
                })
            else:
                # Deactivate Method
                method.active = False

        # Create New methods
        methods_to_create = methods_dict.keys() - set(existing_methods.mapped('method_id_code'))
        MolliePaymentMethod = self.env['mollie.payment.method']
        for method in methods_to_create:
            data = methods_dict[method]

            create_vals = {
                'name': data['description'],
                'method_id_code': data['id'],
                'parent_id': self.id,
                'min_amount': data['minimumAmount'] and data['minimumAmount']['value'] or 0,
                'max_amount': data['maximumAmount'] and data['maximumAmount']['value'] or 0,
                'supports_order_api': data.get('support_order_api', False),
                'supports_payment_api': data.get('support_payment_api', False)
            }

            # Manage issuer for the method
            if data.get('issuers'):
                issuer_ids = []
                for issuer_data in data['issuers']:
                    MollieIssuer = self.env['mollie.payment.method.issuer']
                    issuer = MollieIssuer.search([('issuers_id_code', '=', issuer_data['id'])], limit=1)
                    if not issuer:
                        issuer_create_vals = {
                            'name': issuer_data['name'],
                            'issuers_id_code': issuer_data['id'],
                        }
                        icon = self.env['payment.icon'].search([('name', '=', issuer_data['name'])], limit=1)
                        image_url = issuer_data.get('image', {}).get('size2x')
                        if not icon and image_url:
                            icon = self.env['payment.icon'].create({
                                'name': issuer_data['name'],
                                'image': base64.b64encode(requests.get(image_url).content)
                            })
                        issuer_create_vals['payment_icon_ids'] = [(6, 0, [icon.id])]
                        issuer = MollieIssuer.create(issuer_create_vals)
                    issuer_ids.append(issuer.id)
                if issuer_ids:
                    create_vals['payment_issuer_ids'] = [(6, 0, issuer_ids)]

            # Manage icon for method
            icon = self.env['payment.icon'].search([('name', '=', data['description'])], limit=1)
            image_url = data.get('image', {}).get('size2x')
            if not icon and image_url:
                icon = self.env['payment.icon'].create({
                    'name': data['description'],
                    'image': base64.b64encode(requests.get(image_url).content)
                })
            if icon:
                create_vals['payment_icon_ids'] = [(6, 0, [icon.id])]

            MolliePaymentMethod.create(create_vals)

    def mollie_get_active_methods(self, order=None):
        # TODO: [PGA] Check currency is supported. Hard coded filter can be applied based on https://docs.mollie.com/payments/multicurrency
        methods = self.mollie_methods_ids.filtered(lambda m: m.active and m.active_on_shop)

        if not self.sudo().mollie_profile_id:
            methods = methods.filtered(lambda m: m.method_id_code != 'creditcard')

        # Hide methods if order amount is higher then method limits
        remove_voucher_method = True
        if order and order._name == 'sale.order':
            methods = methods.filtered(lambda m: order.amount_total >= m.min_amount and (order.amount_total <= m.max_amount or not m.max_amount))
            remove_voucher_method = not any(map(lambda p: p._get_mollie_voucher_category(), order.mapped('order_line.product_id.product_tmpl_id')))
        if order and order._name == 'account.move':
            methods = methods.filtered(lambda m: order.amount_residual >= m.min_amount and (order.amount_residual <= m.max_amount or not m.max_amount))
            remove_voucher_method = not any(map(lambda p: p._get_mollie_voucher_category(), order.mapped('invoice_line_ids.product_id.product_tmpl_id')))

        if remove_voucher_method:
            methods = methods.filtered(lambda m: m.method_id_code != 'voucher')

        # Hide only order type methods from transection links
        if request and request.httprequest.path == '/website_payment/pay':
            methods = methods.filtered(lambda m: m.supports_payment_api == True)

        # Hide based on country
        if request:
            country_code = request.session.geoip and request.session.geoip.get('country_code') or False
            if country_code:
                methods = methods.filtered(lambda m: not m.country_ids or country_code in m.country_ids.mapped('code'))

        return methods

    def mollie_form_generate_values(self, tx_values):
        self.ensure_one()
        tx_reference = tx_values.get('reference')
        if not tx_reference:
            error_msg = _('Mollie: received data with missing tx reference (%s)') % (tx_reference)
            _logger.info(error_msg)
            raise ValidationError(error_msg)

        transaction = self.env['payment.transaction'].sudo().search([('reference', '=', tx_reference)])
        base_url = self.get_base_url()
        tx_values['base_url'] = base_url
        tx_values['checkout_url'] = False
        tx_values['error_msg'] = False
        tx_values['status'] = False

        if transaction:

            result = None

            # check if order api is supportable by selected mehtod
            method_record = self._mollie_get_method_record(transaction.mollie_payment_method)
            if method_record.supports_order_api:
                result = self._mollie_create_order(transaction)

            # Fallback to payment method
            # Case: When invoice is partially paid or partner have credit note
            # then mollie can not create order because orderline and total amount is diffrent
            # in that case we have fall back on payment method.
            if (result and result.get('error') or result is None) and method_record.supports_payment_api:
                if result and result.get('error'):
                    _logger.warning("Can not use order api due to '%s' fallback on payment" % (result.get('error')))
                result = self._mollie_create_payment(transaction)

            if result.get('error'):
                tx_values['error_msg'] = result['error']
                self.env.cr.rollback()    # Roll back if there is error
                return tx_values

            if result.get('status') == 'paid':
                transaction.form_feedback(result, "mollie")
            else:
                tx_values['checkout_url'] = result["_links"]["checkout"]["href"]
            tx_values['status'] = result.get('status')
        return tx_values

    def mollie_get_form_action_url(self):
        return "/payment/mollie/action"

    def _mollie_create_order(self, transaction):
        order_source = False
        if transaction.invoice_ids:
            order_source = transaction.invoice_ids[0]
        elif transaction.sale_order_ids:
            order_source = transaction.sale_order_ids[0]

        if not order_source:
            return None

        order_type = 'Sale Order' if order_source._name == 'sale.order' else 'Invoice'

        payment_data = {
            'method': transaction.mollie_payment_method,
            'amount': {
                'currency': transaction.currency_id.name,
                'value': "%.2f" % transaction.amount
            },

            'billingAddress': order_source.partner_id._prepare_mollie_address(),
            "orderNumber": "%s (%s)" % (order_type, transaction.reference),
            'lines': self._mollie_get_order_lines(order_source, transaction),

            'metadata': {
                'transaction_id': transaction.id,
                'reference': transaction.reference,
                'type': order_type,

                # V12 fallback
                "order_id": "ODOO-%s" % (transaction.reference),
                "description": order_source.name
            },

            'locale': self._mollie_user_locale(),
            'redirectUrl': self._mollie_redirect_url(transaction.id),
        }

        # Mollie throws error with local URL
        webhook_url = self._mollie_webhook_url(transaction.id)
        if "://localhost" not in webhook_url and "://192.168." not in webhook_url:
            payment_data['webhookUrl'] = webhook_url

        # Add if transection has cardToken
        if transaction.mollie_payment_token:
            payment_data['payment'] = {'cardToken': transaction.mollie_payment_token}

        # Add if transection has issuer
        if transaction.mollie_payment_issuer:
            payment_data['payment'] = {'issuer': transaction.mollie_payment_issuer}

        result = self._api_mollie_create_order(payment_data)

        # We are setting acquirer reference as we are receiving it before 3DS payment
        # So we can identify transaction with mollie respose
        if result and result.get('id'):
            transaction.acquirer_reference = result.get('id')
        return result

    def _mollie_create_payment(self, transaction):
        """ This method is used as fallback. When order method fails. """
        payment_data = {
            'method': transaction.mollie_payment_method,
            'amount': {
                'currency': transaction.currency_id.name,
                'value': "%.2f" % transaction.amount
            },
            'description': transaction.reference,

            'metadata': {
                'transaction_id': transaction.id,
                'reference': transaction.reference,
            },

            'locale': self._mollie_user_locale(),
            'redirectUrl': self._mollie_redirect_url(transaction.id),
        }

        # Mollie throws error with local URL
        webhook_url = self._mollie_webhook_url(transaction.id)
        if "://localhost" not in webhook_url and "://192.168." not in webhook_url:
            payment_data['webhookUrl'] = webhook_url

        # Add if transection has cardToken
        if transaction.mollie_payment_token:
            payment_data['cardToken'] = transaction.mollie_payment_token

        # Add if transection has issuer
        if transaction.mollie_payment_issuer:
            payment_data['issuer'] = transaction.mollie_payment_issuer

        result = self._api_mollie_create_payment(payment_data)

        # We are setting acquirer reference as we are receiving it before 3DS payment
        # So we can identify transaction with mollie respose
        if result and result.get('id'):
            transaction.acquirer_reference = result.get('id')
        return result

    def _mollie_get_payment_data(self, transection_reference, force_payment=False):
        """ Sending force_payment=True will send payment data even if transection_reference is for order api """
        mollie_data = False
        if transection_reference.startswith('ord_'):
            mollie_data = self._api_mollie_get_order(transection_reference)
        if transection_reference.startswith('tr_'):    # This is not used
            mollie_data = self._api_mollie_get_payment(transection_reference)

        if not force_payment:
            return mollie_data

        transection_id = False
        if mollie_data['resource'] == 'order':
            payments = mollie_data.get('_embedded', {}).get('payments', [])
            if payments:
                # TODO: handle multiple payment for same order
                transection_id = payments[0]['id']
        elif mollie_data['resource'] == 'payment':
            transection_id = mollie_data['id']

        mollie_client = self._api_mollie_get_client()

        # TO-DO: check if mollie_data is same as below line
        return mollie_client.payments.get(transection_id)

    # -----------------------------------------------
    # Methods that uses to mollie python lib
    # -----------------------------------------------

    def _api_mollie_get_client(self):
        mollie_client = MollieClient(timeout=5)
        # TODO: [PGA] Add partical validation for keys e.g. production key should start from live_

        if self.state == 'enabled':
            mollie_client.set_api_key(self.mollie_api_key_prod)
        elif self.state == 'test':
            mollie_client.set_api_key(self.mollie_api_key_test)

        mollie_client.set_user_agent_component('Odoo', service.common.exp_version()['server_version'])
        mollie_client.set_user_agent_component('MollieOdoo', self.env.ref('base.module_payment_mollie_official').installed_version)
        return mollie_client

    def _api_mollie_create_payment(self, payment_data):
        mollie_client = self._api_mollie_get_client()
        try:
            result = mollie_client.payments.create(payment_data)
        except UnprocessableEntityError as e:
            return {'error': str(e)}
        return result

    def _api_mollie_create_order(self, payment_data):
        mollie_client = self._api_mollie_get_client()
        try:
            result = mollie_client.orders.create(payment_data)
        except UnprocessableEntityError as e:
            return {'error': str(e)}
        return result

    def _api_mollie_get_payment(self, tx_id):
        mollie_client = self._api_mollie_get_client()
        return mollie_client.payments.get(tx_id)

    def _api_mollie_get_order(self, tx_id):
        mollie_client = self._api_mollie_get_client()
        return mollie_client.orders.get(tx_id, embed="payments")

    def _api_mollie_get_active_payment_methods(self, api_type=None):
        result = {}

        mollie_client = self._api_mollie_get_client()
        order_methods = mollie_client.methods.list(resource="orders", include='issuers')
        payment_methods = mollie_client.methods.list()

        # Order api will always have more methods then payment api
        if order_methods.get('count'):
            for method in order_methods['_embedded']['methods']:
                method['support_order_api'] = True
                result[method['id']] = method

        if payment_methods.get('count'):
            for method in payment_methods['_embedded']['methods']:
                if method['id'] in result:
                    result[method['id']]['support_payment_api'] = True
                else:
                    method['support_payment_api'] = True
                    result[method['id']] = method

        return result

    def _api_mollie_refund(self, amount, currency, payment_record):
        mollie_client = self._api_mollie_get_client()
        refund = mollie_client.payment_refunds.on(payment_record).create({
            'amount': {
                'value': "%.2f" % amount,
                'currency': currency.name
            }
        })
        return refund

    # -----------------------------------------------
    # Methods that create mollie order payload
    # -----------------------------------------------

    def _mollie_get_order_lines(self, order, transaction):
        lines = []
        if order._name == "sale.order":
            order_lines = order.order_line.filtered(lambda l: not l.display_type)  # ignore notes and section lines
            lines = self._mollie_prepare_so_lines(order_lines, transaction)
        if order._name == "account.move":
            order_lines = order.invoice_line_ids.filtered(lambda l: not l.display_type)  # ignore notes and section lines
            lines = self._mollie_prepare_invoice_lines(order_lines, transaction)
        return lines

    def _mollie_prepare_so_lines(self, lines, transaction):
        result = []
        for line in lines:
            line_data = self._mollie_prepare_lines_common(line)
            line_data.update({
                'quantity': int(line.product_uom_qty),    # TODO: Mollie does not support float. Test with float amount
                'unitPrice': {
                    'currency': line.currency_id.name,
                    'value': "%.2f" % line.price_reduce_taxinc
                },
                'totalAmount': {
                    'currency': line.currency_id.name,
                    'value': "%.2f" % line.price_total,
                },
                'vatRate': "%.2f" % sum(line.tax_id.mapped('amount')),
                'vatAmount': {
                    'currency': line.currency_id.name,
                    'value': "%.2f" % line.price_tax,
                }
            })

            if transaction.mollie_payment_method == 'voucher':
                category = line.product_template_id._get_mollie_voucher_category()
                if category:
                    line_data.update({
                        'category': category
                    })

            result.append(line_data)
        return result

    def _mollie_prepare_invoice_lines(self, lines, transaction):
        """
            Note: Line pricing calculation
            Mollie need 1 unit price with tax included (with discount if any).
            Sale order line we have field for tax included/excluded unit price. But
            Invoice does not have such fields so we need to compute it manually with
            given calculation.

            Mollie needed fields and calculation (Descount is applied all unit price)
            unitPrice: tax included price for single unit
                unitPrice = total_price_tax_included / qty
                totalAmount = total_price_tax_included
                vatRate = total of tax percentage
                vatAmount = total_price_tax_included - total_price_tax_excluded
        """
        result = []
        for line in lines:
            line_data = self._mollie_prepare_lines_common(line)
            line_data.update({
                'quantity': int(line.quantity),    # TODO: Mollie does not support float. Test with float amount
                'unitPrice': {
                    'currency': line.currency_id.name,
                    'value': "%.2f" % (line.price_total / int(line.quantity))
                },
                'totalAmount': {
                    'currency': line.currency_id.name,
                    'value': "%.2f" % line.price_total,
                },
                'vatRate': "%.2f" % sum(line.tax_ids.mapped('amount')),
                'vatAmount': {
                    'currency': line.currency_id.name,
                    'value': "%.2f" % (line.price_total - line.price_subtotal),
                }
            })

            if transaction.mollie_payment_method == 'voucher':
                category = line.product_id.product_tmpl_id._get_mollie_voucher_category()
                if category:
                    line_data.update({
                        'category': category
                    })
            result.append(line_data)

        return result

    def _mollie_prepare_lines_common(self, line):

        product_data = {
            'name': line.name,
            "type": "physical",
        }

        if line.product_id.type == 'service':
            product_data['type'] = 'digital'  # We are considering service product as digital as we don't do shipping for it.

        if 'is_delivery' in line._fields and line.is_delivery:
            product_data['type'] = 'shipping_fee'

        if line.product_id and 'website_url' in line.product_id._fields:
            base_url = self.get_base_url()
            product_data['productUrl'] = urls.url_join(base_url, line.product_id.website_url)

        # Metadata - used to sync delivery data with shipment API
        product_data['metadata'] = {
            'line_id': line.id,
            'product_id': line.product_id.id
        }

        return product_data

    # -----------------------------------------------
    # Helper methods for mollie
    # -----------------------------------------------

    def _mollie_user_locale(self):
        user_lang = self.env.context.get('lang')
        supported_locale = [
            'en_US', 'nl_NL', 'nl_BE', 'fr_FR',
            'fr_BE', 'de_DE', 'de_AT', 'de_CH',
            'es_ES', 'ca_ES', 'pt_PT', 'it_IT',
            'nb_NO', 'sv_SE', 'fi_FI', 'da_DK',
            'is_IS', 'hu_HU', 'pl_PL', 'lv_LV',
            'lt_LT']
        return user_lang if user_lang in supported_locale else 'en_US'

    def _mollie_redirect_url(self, tx_id):
        base_url = self.get_base_url()
        redirect_url = urls.url_join(base_url, MollieController._redirect_url)
        return "%s?tx=%s" % (redirect_url, tx_id)

    def _mollie_webhook_url(self, tx_id):
        base_url = self.get_base_url()
        redirect_url = urls.url_join(base_url, MollieController._notify_url)
        return "%s?tx=%s" % (redirect_url, tx_id)

    def _mollie_get_method_record(self, method_code):
        return self.env['mollie.payment.method'].search([('method_id_code', '=', method_code)], limit=1)

    # -----------------------------------------------
    # Updates related fixes
    # -----------------------------------------------

    @api.model
    def _mollie_update_hook(self):
        # Mollie no longer supporing inghomepay
        _logger.info("Mollie update hook called")
        inghomepay_method = self.env['mollie.payment.method'].search([('method_id_code', '=', 'inghomepay')])
        if inghomepay_method:
            inghomepay_method.write({'active': False})

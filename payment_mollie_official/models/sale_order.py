# -*- coding: utf-8 -*-
import logging
from mollie.api.client import Client

from odoo import api, models, fields, _
from odoo.addons.payment_mollie_official.models.payment_acquirer_method import get_base_url, get_mollie_provider_key

_logger = logging.getLogger(__name__)

PAYLATER_METHODS = ['klarnapaylater']


class SaleOrder(models.Model):
    _inherit = "sale.order"

    _redirect_url = '/payment/mollie/redirect'
    _mollie_client = Client()

    acquirer_method = fields.Many2one('payment.icon',
                                      string='Acquirer Method',
                                      domain="[('provider','=','mollie')]")
    acquirer_reference = fields.Char(
        string='Acquirer Reference',
        readonly=True,
        help='Reference of the order as stored in the acquirer database')

    def get_available_methods(self, method_ids):
        self.ensure_one()
        available_list = []
        currency = self.pricelist_id.currency_id or False
        country = self.partner_invoice_id.country_id or False
        for method in method_ids:
            if self.amount_total > method.maximum_amount or\
                    self.amount_total < method.minimum_amount:
                continue
            if not method.currency_ids and not method.country_ids:
                available_list.append(method)
            elif method.currency_ids and not method.country_ids:
                if currency in method.currency_ids:
                    available_list.append(method)
            elif not method.currency_ids and method.country_ids:
                if country in method.country_ids:
                    available_list.append(method)
            else:
                if currency in method.currency_ids and\
                        country in method.country_ids:
                    available_list.append(method)
        return available_list

    @api.model
    def _get_mollie_order(self, order_id):
        try:
            order = self.sudo().browse(order_id)
            return order
        except Exception as e:
            _logger.info("__Error!_get_mollie_order__ %s" % (e,))
            return False

    @api.model
    def _get_mollie_to_update_order_data(self, order_id, tx_reference, **post):
        order = self.sudo().browse(order_id)
        orderNumber = 'ODOO%s' % (order.id,)
        base_url = get_base_url(self.env)
        method = (order.acquirer_method and
                  order.acquirer_method.acquirer_reference) or 'None'

        billingAddress = order.partner_invoice_id._get_mollie_address()
        order_data = {
            'billingAddress': billingAddress,
            'metadata': {
                'order_id': orderNumber,
                'description': order.name
            },
            'locale': order.partner_id.lang or 'nl_NL',
            'orderNumber': orderNumber,
            'redirectUrl': "%s%s?reference=%s" % (base_url,
                                                  self._redirect_url,
                                                  tx_reference),
            'method': method

        }
        return order_data

    @api.model
    def _get_mollie_order_data(self, order_id, tx_reference, **post):
        order = self.sudo().browse(order_id)
        orderNumber = 'ODOO%s' % (order.id,)
        lines = self.env["sale.order.line"].sudo(
        )._get_mollie_order_line_data(order)
        base_url = get_base_url(self.env)
        if not lines:
            message = _("_____No order lignes__")
            _logger.info(message)
            self.env['provider.log']._post_log({
                'name': message,
                'detail': message,
                'type': 'olive',
            })
            return False

        method = (order.acquirer_method and
                  order.acquirer_method.acquirer_reference)

        billingAddress = order.partner_invoice_id._get_mollie_address()
        order_data = {
            'amount': {
                'value': '%.2f' % float(order.amount_total),
                'currency': order.currency_id.name
            },
            'billingAddress': billingAddress,
            'metadata': {
                'order_id': orderNumber,
                'description': order.name
            },
            'locale': order.partner_id.lang or 'nl_NL',
            'orderNumber': orderNumber,
            'redirectUrl': "%s%s?reference=%s" % (base_url,
                                                  self._redirect_url,
                                                  tx_reference),
            'lines': lines,
        }
        if method:
            order_data.update({'method': method})
        return order_data

    def mollie_orders_create(self, tx_reference):
        self.ensure_one()
        payload = self._get_mollie_order_data(self.id, tx_reference)
        try:
            if not payload:
                message = _('No order data function mollie_orders_create')
                self.env['provider.log']._post_log({
                    'name': message,
                    'detail': message,
                    'type': 'olive',
                })
                return False
            response = self._mollie_client.orders.create(payload,
                                                         embed='payments')
            if response.get("status", "none") == "created":
                self.acquirer_reference = response.get('id', '')

            self.env['sale.order.line']._set_lines_mollie_ref(self.id,
                                                              response)
            self.env['provider.log']._post_log({
                'name': _("Order created"),
                'detail': "%s" % (response,),
                'type': 'green',
            })
            return response
        except Exception as e:
            _logger.info("ERROR! %s" % (e,))
            self.env['provider.log']._post_log({
                'name': _("ERROR! on Create order"),
                'detail': "%s\n %s" % (e, payload),
                'type': 'red',
            })
            return False

    def mollie_orders_get(self):
        self.ensure_one()
        try:
            response = self._mollie_client.orders.get(
                self.acquirer_reference, embed='payments')
            self.env['provider.log']._post_log({
                'name': "Order exist",
                'detail': "%s" % (response,),
                'type': 'green',
            })
            return response
        except Exception as e:
            _logger.info("ERROR! %s" % (e,))
            self.env['provider.log']._post_log({
                'name': _("ERROR! on find order"),
                'detail': e,
                'type': 'red',
            })
            return False

    def mollie_orders_delete(self):
        self.ensure_one()
        try:
            response = self._mollie_client.orders.delete(
                self.acquirer_reference)
            self.env['provider.log']._post_log({
                'name': "Order deleted",
                'detail': "%s" % (response,),
                'type': 'green',
            })
            return response
        except Exception as e:
            _logger.info("ERROR! %s" % (e,))
            self.env['provider.log']._post_log({
                'name': _("ERROR! on delete order"),
                'detail': e,
                'type': 'red',
            })
            return False

    def mollie_orders_update(self, tx_reference):
        self.ensure_one()
        try:
            payload = self._get_mollie_to_update_order_data(
                self.id, tx_reference)
            response = self._mollie_client.orders.update(
                self.acquirer_reference, payload)
            self.env['provider.log']._post_log({
                'name': "Order updated",
                'detail': "%s" % (response,),
                'type': 'green',
            })
            return response
        except Exception as e:
            _logger.info("ERROR! %s" % (e,))
            self.env['provider.log']._post_log({
                'name': _("ERROR! on update order"),
                'detail': e,
                'type': 'red',
            })
            return False

    def mollie_order_sync(self, tx_reference, key=False):
        self.ensure_one()
        if not key:
            key = get_mollie_provider_key(self.env)
        try:
            self._mollie_client.set_api_key(key)
            response = False
            if not self.acquirer_reference:
                response = self.mollie_orders_create(tx_reference)
            else:
                response = self.mollie_orders_get()
                if not response:
                    response = self.mollie_orders_create(tx_reference)
                else:
                    self.mollie_orders_delete()
                    response = self.mollie_orders_create(tx_reference)
            return response
        except Exception as e:
            _logger.info("ERROR! %s" % (e,))
            self.env['provider.log']._post_log({
                'name': _("ERROR! on sync order"),
                'detail': e,
                'type': 'red',
            })
            return False

    def action_go_to_mollie_order(self):
        self.ensure_one()
        return {
            'name': _('OpenMollieOrder'),
            'type': 'ir.actions.act_url',
            'url': 'https://www.mollie.com/dashboard/orders/%s' % (
                self.acquirer_reference or ''),
            'target': 'new',
        }

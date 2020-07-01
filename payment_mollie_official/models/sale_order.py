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
import logging
from mollie.api.client import Client

from odoo import api, models, fields, _
from odoo.addons.payment_mollie_official.models.mollie import\
    get_base_url, get_mollie_provider_key

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

    @api.multi
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

    @api.multi
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

    @api.multi
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

    @api.multi
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

    @api.multi
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

    @api.multi
    def mollie_order_sync(self, tx_reference, key=False):
        self.ensure_one()
        if not key:
            key = get_mollie_provider_key(
                self.env, company_id=self.company_id.id
            )
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
                    # It is necessary that mollie allows me to update an order
#                     if response['amount']['value'] != '%.2f' % float(
#                             self.amount_total):
#                         self.mollie_orders_delete()
#                         response = self.mollie_orders_create(tx_reference)
#                     else:
#                         response = self.mollie_orders_update(tx_reference)
            return response
        except Exception as e:
            _logger.info("ERROR! %s" % (e,))
            self.env['provider.log']._post_log({
                'name': _("ERROR! on sync order"),
                'detail': e,
                'type': 'red',
            })
            return False

    @api.multi
    def action_go_to_mollie_order(self):
        self.ensure_one()
        return {
            'name': _('OpenMollieOrder'),
            'type': 'ir.actions.act_url',
            'url': 'https://www.mollie.com/dashboard/orders/%s' % (
                self.acquirer_reference or ''),
            'target': 'new',
        }


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.depends('price_unit', 'product_id')
    def _get_price_unit_tax(self):
        """
        Compute the amounts of the SO line.
        """
        for line in self:
            price = line.price_unit
            taxes = line.tax_id.compute_all(
                price,
                line.order_id.currency_id,
                line.product_uom_qty,
                product=line.product_id,
                partner=line.order_id.partner_shipping_id
            )
            line.update({
                'price_unit_taxinc': (
                    line.product_uom_qty and taxes['total_included'] /
                    line.product_uom_qty
                ) or 0.0,
            })

    price_unit_taxinc = fields.Monetary(
        compute='_get_price_unit_tax',
        string='Price Unit Tax inc',
        readonly=True, store=True)
    acquirer_reference = fields.Char(
        string='Acquirer Reference',
        readonly=True,
        help='Reference of the line as stored in the acquirer database')

    @api.model
    def _get_mollie_order_line_data(self, order):
        lines = []
        base_url = get_base_url(self.env)
        for line in order.order_line:
            vatRate = 0.0
            for t in line.tax_id:
                if t.amount_type == 'percent':
                    vatRate += t.amount
            discountAmount = (
                line.price_unit_taxinc - line.price_reduce_taxinc
            ) * int(line.product_uom_qty)
            line_data = {
                'type': "physical",
                'name': line.name,
                'quantity': int(line.product_uom_qty),  # TO BE REVIEWD (float)
                'unitPrice': {
                    "currency": line.currency_id.name,
                    "value": '%.2f' % float(line.price_unit_taxinc)},
                'discountAmount': {
                    "currency": line.currency_id.name,
                    "value": '%.2f' % float(discountAmount)},
                # int(line.product_uom_qty) TO BE REVIEWD (float)
                'totalAmount': {
                    "currency": line.currency_id.name,
                    "value": '%.2f' % float(line.price_total)},
                'vatRate': '%.2f' % float(vatRate),
                'vatAmount': {
                    "currency": line.currency_id.name,
                    "value": '%.2f' % float(line.price_tax)},
                'productUrl': '%s/line/%s' % (base_url, line.id),
            }
            lines.append(line_data)
        return lines

    @api.model
    def _set_lines_mollie_ref(self, order_id, response):
        if not response.get('lines', False):
            _logger.info("Error!___No line in response _____")
            return False

        for line in response['lines']:
            if not line.get('_links', False):
                _logger.info("___No line _links _____")
                continue
            if not line['_links'].get('productUrl', False):
                _logger.info("Error!___No line _links _productUrl____")
                continue
            productUrl_dic = line['_links']['productUrl']
            productUrl = productUrl_dic.get("href", "")
            splits = productUrl.split("/")
            line_id = int(splits[-1]) or False
            if not isinstance(line_id, int):
                _logger.info("Error!___line_id is not integer____")
                continue
            order_line = self.search([
                ('order_id', '=', order_id),
                ('id', '=', line_id),
            ])
            if len(order_line) == 1:
                order_line.acquirer_reference = line.get('id', '')
            else:
                _logger.info("Error!___Many line with same ID____")
                continue
        return True
